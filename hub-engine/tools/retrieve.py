"""混合检索：确定性通道（按 type/tag 精确/词级命中）+ 语义通道（n-gram/分词 余弦召回）

第一层性能优化（2026-08-18）：进程内 `_CorpusIndex`
- 惰性扫描一次 active 卡，构建 type/tag 倒排索引（确定性通道 O(命中)）
- token counts 按 (path, mtime, size, mode, n) 缓存，jieba 分词只在卡片变更时重算
- 目录签名做失效校验：卡片增删改后自动重建索引，行为/顺序与逐次全扫完全一致

第二层向量融合（2026-08-18）：语义通道上叠加稠密向量召回（bge-small-zh + SQLite）
- `semantic_vector_retrieve`：读 .sync/vector.db 做向量余弦召回（只读，不触发 build）
- `_fused_semantic`：始终并行——词袋 + 向量两通道同时打分，RRF 融合取 top_k
- 退化：向量后端未装/未建库 → 通道返回空 → 融合等价单通道，0 行为回归
"""

import contextlib
from collections import Counter
from pathlib import Path

from common.frontmatter import Card, try_read_card
from common.vector import build_idf, cosine, tokenize, vector

# 参与检索的卡片目录（五大类型与 INDEX.md 一致；经验卡 experience 必须参与，
# 2026-09-02 bf8f49b 误将其移出导致真实回归 67%→恢复；libs/retro 非五类不纳入主检索）
_ACTIVE_DIRS = (
    "rules",
    "blueprints",
    "methodology",
    "longterm",
    "projects",
    "experience",
)

# 不参与检索的卡片状态（单一事实源）
#   archived   —— 已归档
#   deprecated —— 已作废（内容并入 frontmatter.superseded_by）
# 2026-09-23：deprecated 改为显式字段。此前靠「DEPRECATED 注释在文件第 1 行 ⇒
# frontmatter 解析失败 ⇒ 卡被丢弃」被动排除，位置敏感：为加 tier 而把注释下移
# 会让卡"复活"进检索库（A5 踩坑）。
# 同日：已删除历史上第二套重复引擎（AgentMemoryHub/hub-engine）——它写过同一个
# 语义但口径不同，本仓 common/frontmatter.py 的 VALID_STATUS 必须与之保持一致。
EXCLUDED_STATUSES = frozenset({"archived", "deprecated"})

# 第二层向量融合（方案 A：bge-small-zh + SQLite）
_RRF_K = 60  # RRF rank 常数：rank 分 = 1/(k+rank)，k 越大末位影响越小
_VEC_POOL = 20  # 融合前每个通道的召回池大小（>top_k，给次要通道上榜机会）

# 通道权重：向量通道分数更可信（词袋通道在中文短查询上噪声大）。
# 2026-09-24 实测（22 条金标准，word 模式，recall@5 / recall@1）：
#   等权 1.0/1.0 → 95% / 77% ；word 1.0 / vec 1.5 → 95% / 82% ；vec 2.0 → 95% / 86%
# 取 1.5：拿满 recall@1 收益且改动最温和（配合冠军保底后 100% / 86%）。
_WORD_WEIGHT = 1.0
_VEC_WEIGHT = 1.5

# 英文功能词（停用词）：word 分支 `w in t` 子串匹配会因 "to/for/how" 等
# 命中几乎所有含 tool/token 等 tag，这里过滤掉避免英文查询过度命中全库
_EN_STOP = {
    "a",
    "an",
    "i",
    "is",
    "am",
    "are",
    "was",
    "were",
    "be",
    "been",
    "the",
    "to",
    "of",
    "for",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "how",
    "what",
    "why",
    "who",
    "when",
    "where",
    "which",
    "do",
    "does",
    "did",
    "not",
    "you",
    "your",
    "my",
    "we",
    "our",
    "with",
    "as",
    "by",
    "from",
    "up",
    "down",
    "out",
    "over",
    "than",
    "then",
    "just",
    "can",
    "use",
    "get",
    "way",
    "go",
    "there",
}


# 反触发罚分（内化自 paulpas/agent-skill-router 路径B）：query 命中卡片声明的
# anti_trigger 词条时，扣其语义分，防通用/大面卡片抢占特定任务查询（复用 _EN_STOP 粒度）。
_ANTI_PENALTY = 0.15  # 每命中一条扣分
_ANTI_CAP = 0.5  # 单卡累计扣分封顶


def _anti_triggers(card: Card) -> set[str]:
    """读取卡片 frontmatter 的 anti_trigger（list / 逗号|空格 / 连字符分隔），归一为小写词集。

    anti_trigger 表示「该卡不适用/禁止命中的语义场景」，配合负路由边界做语义侧降权。
    """
    raw = card.extra.get("anti_trigger")
    if not raw:
        return set()
    atoms = raw if isinstance(raw, list) else str(raw).replace(",", " ").replace("|", " ").split()
    out: set[str] = set()
    for a in atoms:
        for t in tokenize(str(a), mode="word"):
            if len(t) >= 2 and t not in _EN_STOP:
                out.add(t)
    return out


def _card_text(c: Card) -> str:
    return c.body + " " + " ".join(c.tags)


class _CorpusIndex:
    """进程内记忆语料索引：一次扫描 + 倒排 + token counts 缓存（mtime 失效）。"""

    __slots__ = ("_counts", "_paths", "_tag_index", "cards")

    def __init__(self, root: Path) -> None:
        self.cards: list[Card] = []
        self._paths: dict[str, tuple[int, int]] = {}  # abs_path -> (mtime_ns, size)
        self._counts: dict[tuple[str, str, int], object] = {}  # (abs_path, mode, n) -> Counter
        self._tag_index: dict[str, list[Card]] | None = None  # 懒建（见 tag_index()）
        seen: set[str] = set()
        for sub in _ACTIVE_DIRS:
            d = root / sub
            if not d.exists():
                continue
            for p in sorted(d.glob("*.md")):
                abs_p = str(p)
                if abs_p in seen:
                    continue
                seen.add(abs_p)
                c = try_read_card(p)
                # 不参与检索的状态：archived（归档）+ deprecated（已作废，内容并入 superseded_by）
                # 2026-09-23：deprecated 此前靠「注释在文件第 1 行导致 frontmatter 解析失败」
                # 被动排除——位置敏感且不可测。现改为显式 status，与中枢 cards.EXCLUDED_STATUSES 同口径。
                if c is None or c.status in EXCLUDED_STATUSES:
                    continue
                self.cards.append(c)
                st = p.stat()
                self._paths[abs_p] = (st.st_mtime_ns, st.st_size)

    def tag_index(self) -> dict[str, list[Card]]:
        """tag/type 倒排索引：**懒建 + 随语料索引缓存**。

        以前每次 `deterministic_retrieve` 都重跑 `_build_tag_index(cards)`（446 卡）——
        实测 **68–71 ms/次**，占端到端（稳态 ~340 ms）的两成。索引已随目录签名缓存，
        倒排同理可缓存；带 tags 过滤时仍是子集，走原重算路径（行为不变）。
        """
        if self._tag_index is None:
            self._tag_index = _build_tag_index(self.cards)
        return self._tag_index

    def counts(self, card: Card, mode: str, n: int):
        """卡片 token 计数向量（缓存到检索入口，mtime 变化即 cache 失效/重建）"""
        key = (str(card.path), mode, n)
        cached = self._counts.get(key)
        if cached is not None:
            return cached
        vec = vector(_card_text(card), n=n, mode=mode)
        # path 不可哈希时放弃缓存，退化为逐次计算
        with contextlib.suppress(TypeError):
            self._counts[key] = vec
        return vec


# 缓存：root 绝对路径 -> (目录签名, 索引)。签名含每文件 (mtime_ns, size)，变化即重建
_INDEX_CACHE: dict[str, tuple[tuple, _CorpusIndex]] = {}
# IDF 结果缓存：按 (root_str, mode, n) 索引；语料签名变化（_dir_signature）时自动失效
# 避免每次 semantic 查询重跑 build_idf（198 卡 jieba 分词 + DF 统计 = 831ms）
_IDF_CACHE: dict[tuple[str, str, int, int], dict[str, float]] = {}


def _dir_signature(root: Path) -> tuple:
    """目录签名：各活动目录下 `*.md` 的 (绝对路径, mtime_ns, size)。变了就重建索引/IDF。

    2026-09-25（P2-e 剖析）：改用 `os.scandir`（Windows 下目录枚举自带 stat 缓存）
    代替 `sorted(d.glob()) + p.stat()`——446 个文件的签名从 **~70 ms 降至个位数 ms**，
    而它每次检索都要跑（占稳态 ~340 ms 的两成）。语义不变：仍以 (路径, mtime_ns, size) 为准。
    """
    import os

    sig: list[tuple[str, int, int]] = []
    for sub in _ACTIVE_DIRS:
        d = root / sub
        if not d.exists():
            continue
        try:
            with os.scandir(d) as it:
                rows: list[tuple[str, int, int]] = []
                for entry in it:
                    if not entry.name.lower().endswith(".md"):
                        continue
                    try:
                        st = entry.stat()
                    except OSError:
                        continue
                    rows.append((os.path.abspath(entry.path), st.st_mtime_ns, st.st_size))
        except OSError:
            continue
        sig.extend(sorted(rows))
    return tuple(sig)


def _index(root: Path) -> _CorpusIndex:
    """取（或重建）root 的进程内存检索索引；卡片变更时自动失效重建。"""
    key = str(Path(root).resolve())
    sig = _dir_signature(Path(root))
    hit = _INDEX_CACHE.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    idx = _CorpusIndex(Path(root))
    _INDEX_CACHE[key] = (sig, idx)
    # 语料变了 → 清空该 root 的 IDF 缓存（其他 root 的不受影响）
    stale_keys = [k for k in _IDF_CACHE if k[0] == key]
    for k in stale_keys:
        _IDF_CACHE.pop(k, None)
    return idx


def _build_tag_index(cards: list[Card]) -> dict[str, list[Card]]:
    """tag（小写）→ 卡片列表 倒排索引；含 type 映射到 `type:<type>` 键，供 type 检索复用"""
    inv: dict[str, list[Card]] = {}
    for c in cards:
        inv.setdefault(f"type:{c.type}", []).append(c)
        for t in c.tags:
            inv.setdefault(t.lower(), []).append(c)
    return inv


def _clear_index_for(root: Path) -> None:
    """测试/外部改动后强制清空 root 的索引缓存（供单测校验缓存重建）"""
    _INDEX_CACHE.pop(str(Path(root).resolve()), None)


def _filter_cards_by_tags(cards: list[Card], tags: list[str] | None) -> list[Card]:
    """按标签 AND 组合路由：候选集 = 同时含所有 `tags`（小写）的卡。

    tags 为空/None → 返回全部（0 回归）。
    用途（2026-09-02）：把全库 138 张按「叠加标签」收窄为精确子集，
    如 tags=[\"cad\", \"methodology\"] 只留「既是 CAD 经验又是方法论」的卡，
    供后续排序时不被其他主题噪声淹没——次路由的知识导航层实现。
    """
    if not tags:
        return cards
    wanted = {t.lower().strip() for t in tags if t and t.strip()}
    if not wanted:
        return cards
    out = []
    for c in cards:
        have = {t.lower().strip() for t in c.tags}
        if wanted <= have:  # 所有指定标签都命中（AND）
            out.append(c)
    return out


def deterministic_retrieve(root: Path, query: str, mode: str = "word", tags: list[str] | None = None) -> list[Card]:
    """确定性通道：query 命中 type 或 tag 即返回（走倒排索引，O(命中)）。

    - char 模式：整句包含（原行为）
    - word 模式：额外支持词级匹配——query 任一分词与 tag 互相包含即命中
      （如查询含 "dll" 可命中 tag "dll-lock"，无需精确整句）
    - tags：可选「叠加标签」AND 路由过滤——先收窄候选集，再命中排序

    返回按「命中信号分」降序排序：type 精确命中=3 分、tag 精确子串=2 分、word 命中 tag=1+hits 分；
    多 tag 命中的卡排前，避免调用方取 top_k 时被噪声淹没（2026-08-31 补排序）。
    """
    q = query.lower()
    q_words = tokenize(query, mode="word") if mode == "word" else []
    # 过滤无意义的英文词（停用词 + 单字符），避免 word 分支 `w in t` 误命中几乎全部 tag
    q_words = [w for w in q_words if len(w) >= 2 and w not in _EN_STOP]
    idx = _index(root)
    # 叠加标签 AND 路由：先按 tags 收窄候选集（0 回归），再在其内建索引/命中
    cards = _filter_cards_by_tags(idx.cards, tags)
    # 无 tags 过滤时复用索引里缓存的倒排（有过滤时是子集，需重算）
    inv = _build_tag_index(cards) if tags else idx.tag_index()
    # id -> 命中信号分
    score: dict[int, int] = {}

    def _add(card_id: int, pts: int) -> None:
        score[card_id] = score.get(card_id, 0) + pts

    for c in cards:
        if q in c.type:
            _add(id(c), 3)
    tkey = f"type:{q}"
    for c in inv.get(tkey, []):
        _add(id(c), 3)
    for t in inv:
        if t.startswith("type:"):
            continue
        if q in t:
            # 精确子串匹配（最强信号）
            for c in inv[t]:
                _add(id(c), 2)
        # 子串匹配和分词匹配同时累积，独立 if 而非 elif
        # 2026-09-01 修复：原 elif 导致精确 tag 子串匹配 (+2) 被分词命中 (+3) 反超
        if q_words:
            hits = sum(1 for w in q_words if w in t)
            hit_words = [w for w in q_words if w in t]
            hit_english = any(not all("\u4e00" <= ch <= "\u9fff" for ch in w) for w in hit_words)
            threshold = (
                2
                if (
                    hit_english
                    and len(q_words) >= 2
                    and all(not all("\u4e00" <= ch <= "\u9fff" for ch in w) for w in q_words)
                )
                else 1
            )
            if hits >= threshold:
                for c in inv[t]:
                    _add(id(c), 1 + hits)  # 命中词越多分越高

    matched_ids = set(score.keys())
    # 按命中分降序，同分保持 cards（tag 过滤后）原始顺序（稳定）
    return sorted(
        [c for c in cards if id(c) in matched_ids],
        key=lambda card: score[id(card)],
        reverse=True,
    )


def _semantic_scored(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "char"
) -> list[tuple[Card, float]]:
    """语义通道带分数召回：返回 [(card, sim)]，按相似度降序。

    默认 char（2026-08-31 改）：
    - char：字符 n-gram（实测 n=2 最优；混合 top3 recall 100% vs word 73%；纯 n-gram 无 IDF 开销）
    - word：jieba 分词 + IDF 加权（语料内稀有词权重更高，缓解领域共词抢占；IDF 结果会缓存到 _IDF_CACHE）
    """
    idx = _index(root)
    idf = None
    if mode == "word":
        # IDF 缓存：key=(root_str, mode, n, n_cards)，语料签名变化由 _index() 里清 _IDF_CACHE 兜底
        cache_key = (str(Path(root).resolve()), mode, n, len(idx.cards))
        idf = _IDF_CACHE.get(cache_key)
        if idf is None:
            texts = [_card_text(c) for c in idx.cards]
            idf = build_idf(texts, n=n, mode=mode)
            _IDF_CACHE[cache_key] = idf
    qv = vector(query, n=n, mode=mode, idf=idf)
    # 反触发：word 模式下取查询词集，供逐卡判是否命中其 anti_trigger（降权）
    q_tokens = (
        {t for t in tokenize(query, mode="word") if len(t) >= 2 and t not in _EN_STOP} if mode == "word" else set()
    )
    scored = []
    for c in idx.cards:
        cv = idx.counts(c, mode, n)
        if idf:
            # 缓存的是未加权计数，这里按语料 IDF 统一加权后再比余弦
            cv = Counter({tok: cnt * idf.get(tok, 1.0) for tok, cnt in cv.items()})
        sim = cosine(qv, cv)
        if sim > 0:
            if q_tokens:
                hits = sum(1 for at in _anti_triggers(c) if at in q_tokens)
                if hits:
                    sim -= min(hits * _ANTI_PENALTY, _ANTI_CAP)
            if sim > 0:
                scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(c, sim) for sim, c in scored[:top_k]]


def semantic_retrieve(root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "char") -> list[Card]:
    """语义通道：对 body+tags 做 token 余弦相似度召回 top-k（兼容旧接口）"""
    return [c for c, _ in _semantic_scored(root, query, top_k, n, mode)]


def _norm_card_path(p: object, root: Path) -> str:
    r"""归一为绝对小写路径（Windows 大小写不敏感），**不依赖进程 CWD**。

    ⚠️ 相对路径必须按 `root` 解析，不能靠 `Path.resolve()` 的隐式 CWD。

    历史 bug（2026-09-23 记录）：建库侧存的是 `str(card.path)`，若建库时 `--root` 是
    相对路径，库里就落下相对路径；而检索侧只 `Path(p).resolve()`，按**进程 CWD** 解析
    ⇒ 仅当 CWD 恰好是项目根时才匹配。实测：cwd=项目根 向量 3/6；
    cwd=hub-engine 或**任何非项目根目录**时，向量 **0/6 静默退化**（路径按进程 CWD 解不开）。
    生产 MCP 以绝对 `--hub-root` 启动、CWD 继承父进程 ⇒ 向量通道可能长期静默失效。

    建库侧已于 2026-09-24 改为存绝对路径（`semsearch.build`）；此处再加一层防御：
    相对路径按 `root` 解析，并兼容「含 `AgentMemoryHub` 前缀」等历史形态（即相对的是
    root 的父目录）。旧实现是 `semantic_vector_retrieve` 内的闭包，无法单测；
    上提为模块级以便对 CWD 独立性做回归测试。
    """
    pp = Path(p) if not isinstance(p, Path) else p
    if not pp.is_absolute():
        cand = Path(root) / pp
        if not cand.exists():
            # 兼容库里存的是「相对 root 的父目录」（如 AgentMemoryHub\\rules\\x.md）
            alt = Path(root).parent / pp
            if alt.exists():
                cand = alt
        pp = cand
    try:
        return str(pp.resolve()).lower()
    except OSError:
        return str(pp).replace("\\", "/").lower()


def semantic_vector_retrieve(root: Path, query: str, top_k: int = 5) -> list[tuple[Card, float]]:
    """向量通道（第二层）：embed(query) 与库内每卡向量点积(余弦) 召回 top_k [(card, score)]。

    仅做读库，不触发 build（建库由独立 build 流程负责）。
    后端不可用 / 未建库(.sync/vector.db) → 返回 [] → 融合自动退化，无行为回归。
    """
    from tools import semsearch  # 惰性导入，避免与 semsearch 循环引用

    qv = semsearch.query_embedded(query)
    if qv is None:
        return []

    path_to_card = {_norm_card_path(c.path, root): c for c in _index(root).cards}
    out = []
    for p, s in semsearch.vector_scores(root, qv, top_k=top_k):
        c = path_to_card.get(_norm_card_path(p, root))
        if c is not None:
            out.append((c, s))
    return out


def _det_is_decisive(query: str, cards: list[Card]) -> bool:
    """确定性结果是否「足以定论」（可短路、不必走语义/向量通道）。

    判定：是否存在一张命中卡**覆盖了查询的全部词**（或整句命中 type/tag）。

    为何必须加这道门（2026-09-24 修复）：旧代码是 `if hits:` —— **只要有命中就短路**。
    而 `deterministic_retrieve` 在 word 模式下按「查询词 ⊂ tag」匹配，
    **部分词命中也算命中**，于是：

    - 「写锁 僵尸」→ 某卡 tag 叫 `写锁`（只命中 1/2 词）→ 返回 1 张 → **短路**
    - 「embedding model switch drift」→ 英文查询阈值为 2，只有 tag `model-switch`
      命中 2 词 → 返回 `deepseek-peak-offpeak-scheduler` → **短路**

    结果：好通道（词袋 + 向量，纯 RRF 下目标卡均在**第 1 名**）全被跳过。
    实测生产模式（word）recall@1 **75% → 5%**。

    弱信号不再短路，而是交给语义通道；强信号（全部词命中）仍走快路径。
    """
    q = query.strip().lower()
    if not q:
        return False
    words = [w for w in tokenize(query, mode="word") if len(w) >= 2 and w not in _EN_STOP]
    for c in cards:
        tags = [str(t).lower() for t in (getattr(c, "tags", None) or [])]
        ctype = str(getattr(c, "type", "") or "").lower()
        # 强信号 1：整句命中 type
        if ctype and q in ctype:
            return True
        # 强信号 2：整句命中某个 tag（如查询就是 "写锁"）
        if any(q in t for t in tags):
            return True
        # 强信号 3：**全部**查询词都命中该卡 tag（部分命中不算）
        if words and all(any(w in t for t in tags) for w in words):
            return True
    return False


def _rrf_fuse(
    word_scored,
    vec_scored,
    top_k: int,
    k: int = _RRF_K,
    w_word: float = _WORD_WEIGHT,
    w_vec: float = _VEC_WEIGHT,
) -> list[tuple[Card, float]]:
    """RRF（Reciprocal Rank Fusion）合并两条按位序排序的召回，取前 top_k。

    任意卡片某通道缺失时该通道贡献为 0；score 为两通道 rank 分之和（非余弦原始值）。
    权重依据见 `_WORD_WEIGHT` / `_VEC_WEIGHT` 旁的实测表。
    """
    ranks_word = {id(c): r for r, (c, _) in enumerate(word_scored, 1)}
    ranks_vec = {id(c): r for r, (c, _) in enumerate(vec_scored, 1)}
    card_by_id = {id(c): c for c, _ in [*word_scored, *vec_scored]}
    summed = {}
    for cid in ranks_word.keys() | ranks_vec.keys():
        s = (w_word / (k + ranks_word[cid])) if cid in ranks_word else 0.0
        s += (w_vec / (k + ranks_vec[cid])) if cid in ranks_vec else 0.0
        summed[cid] = s
    ranked = sorted(summed.items(), key=lambda kv: kv[1], reverse=True)
    return [(card_by_id[cid], summed[cid]) for cid, _ in ranked[:top_k]]


def _with_vector_champion(fused: list[tuple[Card, float]], vec_scored, top_k: int) -> list[tuple[Card, float]]:
    """向量冠军保底：向量通道第 1 名若被融合挤出，补进首位。

    为什么需要（2026-09-24 实测，P0-B 真因）：RRF 只看位序不看强度。
    一条**只有向量命中**的卡（如 `hypothesis-property-based-testing-blueprint`，
    向量相似度 **0.6704**，领先第 2 名 0.107）在词袋通道无名次，而排在 2-6 位的
    普通卡因「两通道都上榜」各得两份 rank 分而反超它 —— 强证据被判负，目标掉出 top-5。

    语义上：向量通道的**榜首**是单条最强的语义证据；若融合把它挤掉，说明融合在
    掩盖证据而不是综合证据。故保底保留它并置首位 —— 实测 recall@5 95%→**100%**，
    唯一未命中项（即上述蓝图）被救回。这是 `_fused_semantic` 里「通道退化自修复」
    的推广：退化阈值只处理‘整条通道失效’，本函数处理‘单条强证据被淹没’。
    """
    if not vec_scored:
        return fused[:top_k]
    champ = vec_scored[0][0]
    champ_path = str(getattr(champ, "path", "") or "")
    if champ_path and any(str(getattr(c, "path", "") or "") == champ_path for c, _ in fused):
        return fused[:top_k]
    return [(champ, 0.0), *fused[: top_k - 1]]


def _fused_semantic(root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "char") -> list[tuple[Card, float]]:
    """词袋 + 向量双路 RRF 融合，带通道退化自修复（方案 A，2026-08-31）。

    当某通道严重退化（返回数 < pool 的 10%）时直接返回另一通道结果，
    避免"双通道都命中"的少数卡用两个 rank 分相加反超"只有好通道命中"的真实目标
    （典型场景：英文改写查询 -> 词袋 n-gram 余弦几乎全 0 -> 只返回 1-2 张卡）。

    向量后端未装/未建库 -> 该通道返回空 -> 融合等价单通道，行为与现状一致（0 回归）。
    """
    pool = max(top_k * 2, _VEC_POOL)
    word_scored = _semantic_scored(root, query, top_k=pool, n=n, mode=mode)
    vec_scored = semantic_vector_retrieve(root, query, top_k=pool)

    # 退化阈值：返回卡数低于 pool 的 10% 视为该通道失效
    floor = max(pool // 10, 2)
    w_deg = len(word_scored) < floor
    v_deg = len(vec_scored) < floor

    if w_deg and v_deg:
        # 双通道都严重退化（极罕见），兜底返回两者合并去重取 top_k
        merged = sorted(
            {id(c): (c, s) for c, s in [*word_scored, *vec_scored]}.values(),
            key=lambda x: x[1],
            reverse=True,
        )
        return merged[:top_k]
    if w_deg:
        return vec_scored[:top_k]
    if v_deg:
        return word_scored[:top_k]
    return _with_vector_champion(_rrf_fuse(word_scored, vec_scored, top_k), vec_scored, top_k)


def retrieve_with_meta(
    root: Path,
    query: str,
    top_k: int = 5,
    n: int = 2,
    mode: str = "word",
    tags: list[str] | None = None,
) -> tuple[str, list[tuple[Card, float | None]]]:
    """混合检索入口，带通道与分数：返回 (channel, [(card, score|None)])

    channel: "empty"（空查询）| "deterministic"（确定性命中，score=None）| "semantic"
    tags: 可选「叠加标签」AND 路由过滤（次路由知识导航），透传给确定性通道

    mode 默认由 `char` 改为 `word`（2026-09-24）：此前 MCP（`word`）与 CLI（`word`）
    都是 word，而**函数默认是 char**，三处不一致。实测（20 条金标准 recall@5）：
    word **100%** / char 90%（recall@1：80% / 75%）—— 旧的「char 更优」结论
    （docstring 里的 2026-08-31 记录）是在短路 bug 存在时得出的，已被推翻。
    """
    if not query.strip():
        return "empty", []
    hits = deterministic_retrieve(root, query, mode, tags=tags)
    if hits and _det_is_decisive(query, hits):
        return "deterministic", [(c, None) for c in hits]
    return "semantic", _fused_semantic(root, query, top_k, n, mode)


def retrieve(
    root: Path,
    query: str,
    top_k: int = 5,
    n: int = 2,
    mode: str = "word",
    tags: list[str] | None = None,
) -> list[Card]:
    """混合检索入口（兼容旧接口，仅返回卡片列表）

    n: 字符 n-gram 长度（char 模式），默认 2
    mode: "word"（默认，jieba 分词 + IDF）或 "char"（字符 n-gram，零依赖回退）
    tags: 可选「叠加标签」AND 路由过滤——多标签组合精确定位（次路由知识导航）

    默认由 `char` 改为 `word`（2026-09-24，同 `retrieve_with_meta`）。
    """
    _, scored = retrieve_with_meta(root, query, top_k, n, mode, tags=tags)
    return [c for c, _ in scored]
