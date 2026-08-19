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

from collections import Counter
from pathlib import Path

from common.frontmatter import Card, try_read_card
from common.vector import build_idf, cosine, tokenize, vector

# 参与检索的卡片目录（与历史 _walk_active_cards 枚举顺序一致，用于保持返回顺序）
_ACTIVE_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "experience",
    "libs",
    "retro",
    "blueprints",
)

# 第二层向量融合（方案 A：bge-small-zh + SQLite）
_RRF_K = 60  # RRF rank 常数：rank 分 = 1/(k+rank)，k 越大末位影响越小
_VEC_POOL = 20  # 融合前每个通道的召回池大小（>top_k，给次要通道上榜机会）

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
    atoms = (
        raw
        if isinstance(raw, list)
        else str(raw).replace(",", " ").replace("|", " ").split()
    )
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

    __slots__ = ("_counts", "_paths", "cards")

    def __init__(self, root: Path) -> None:
        self.cards: list[Card] = []
        self._paths: dict[str, tuple[int, int]] = {}  # abs_path -> (mtime_ns, size)
        self._counts: dict[
            tuple[str, str, int], object
        ] = {}  # (abs_path, mode, n) -> Counter
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
                if c is None or c.status == "archived":
                    continue
                self.cards.append(c)
                st = p.stat()
                self._paths[abs_p] = (st.st_mtime_ns, st.st_size)

    def counts(self, card: Card, mode: str, n: int):
        """卡片 token 计数向量（缓存到检索入口，mtime 变化即 cache 失效/重建）"""
        key = (str(card.path), mode, n)
        cached = self._counts.get(key)
        if cached is not None:
            return cached
        vec = vector(_card_text(card), n=n, mode=mode)
        try:
            self._counts[key] = vec
        except TypeError:
            pass  # path 不可哈希时放弃缓存，退化为逐次计算
        return vec


# 缓存：root 绝对路径 -> (目录签名, 索引)。签名含每文件 (mtime_ns, size)，变化即重建
_INDEX_CACHE: dict[str, tuple[tuple, _CorpusIndex]] = {}


def _dir_signature(root: Path) -> tuple:
    sig = []
    for sub in _ACTIVE_DIRS:
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                st = p.stat()
            except OSError:
                continue
            sig.append((str(p.resolve()), st.st_mtime_ns, st.st_size))
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


def deterministic_retrieve(root: Path, query: str, mode: str = "word") -> list[Card]:
    """确定性通道：query 命中 type 或 tag 即返回（走倒排索引，O(命中)）。

    - char 模式：整句包含（原行为）
    - word 模式：额外支持词级匹配——query 任一分词与 tag 互相包含即命中
      （如查询含 "dll" 可命中 tag "dll-lock"，无需精确整句）
    """
    q = query.lower()
    q_words = tokenize(query, mode="word") if mode == "word" else []
    # 过滤无意义的英文词（停用词 + 单字符），避免 word 分支 `w in t` 误命中几乎全部 tag
    q_words = [w for w in q_words if len(w) >= 2 and w not in _EN_STOP]
    idx = _index(root)
    inv = _build_tag_index(idx.cards)
    matched: set[int] = set()
    for c in idx.cards:
        if q in c.type:
            matched.add(id(c))
    tkey = f"type:{q}"
    for c in inv.get(tkey, []):
        matched.add(id(c))
    tags_to_check = list(inv.keys())
    for t in tags_to_check:
        if t.startswith("type:"):
            continue
        if q in t or (q_words and any(w in t or t in w for w in q_words)):
            for c in inv[t]:
                matched.add(id(c))
    return [c for c in idx.cards if id(c) in matched]


def _semantic_scored(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[tuple[Card, float]]:
    """语义通道带分数召回：返回 [(card, sim)]，按相似度降序。

    - char：字符 n-gram（实测 n=2 最优）
    - word：jieba 分词 + IDF 加权（语料内稀有词权重更高，缓解领域共词抢占）
    """
    idx = _index(root)
    texts = [_card_text(c) for c in idx.cards]
    idf = build_idf(texts, n=n, mode=mode) if mode == "word" else None
    qv = vector(query, n=n, mode=mode, idf=idf)
    # 反触发：word 模式下取查询词集，供逐卡判是否命中其 anti_trigger（降权）
    q_tokens = (
        {t for t in tokenize(query, mode="word") if len(t) >= 2 and t not in _EN_STOP}
        if mode == "word"
        else set()
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


def semantic_retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """语义通道：对 body+tags 做 token 余弦相似度召回 top-k（兼容旧接口）"""
    return [c for c, _ in _semantic_scored(root, query, top_k, n, mode)]


def semantic_vector_retrieve(
    root: Path, query: str, top_k: int = 5
) -> list[tuple[Card, float]]:
    """向量通道（第二层）：embed(query) 与库内每卡向量点积(余弦) 召回 top_k [(card, score)]。

    仅做读库，不触发 build（建库由独立 build 流程负责）。
    后端不可用 / 未建库(.sync/vector.db) → 返回 [] → 融合自动退化，无行为回归。
    """
    from tools import semsearch  # 惰性导入，避免与 semsearch 循环引用

    qv = semsearch.query_embedded(query)
    if qv is None:
        return []
    path_to_card = {str(c.path): c for c in _index(root).cards}
    out = []
    for p, s in semsearch.vector_scores(root, qv, top_k=top_k):
        c = path_to_card.get(p)
        if c is not None:
            out.append((c, s))
    return out


def _rrf_fuse(
    word_scored, vec_scored, top_k: int, k: int = _RRF_K
) -> list[tuple[Card, float]]:
    """RRF（Reciprocal Rank Fusion）合并两条按位序排序的召回，取前 top_k。

    任意卡片某通道缺失时该通道贡献为 0；score 为两通道 rank 分之和（非余弦原始值）。
    """
    ranks_word = {id(c): r for r, (c, _) in enumerate(word_scored, 1)}
    ranks_vec = {id(c): r for r, (c, _) in enumerate(vec_scored, 1)}
    card_by_id = {id(c): c for c, _ in [*word_scored, *vec_scored]}
    summed = {}
    for cid in ranks_word.keys() | ranks_vec.keys():
        s = (1.0 / (k + ranks_word[cid])) if cid in ranks_word else 0.0
        s += (1.0 / (k + ranks_vec[cid])) if cid in ranks_vec else 0.0
        summed[cid] = s
    ranked = sorted(summed.items(), key=lambda kv: kv[1], reverse=True)
    return [(card_by_id[cid], summed[cid]) for cid, _ in ranked[:top_k]]


def _fused_semantic(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[tuple[Card, float]]:
    """始终并行：词袋(n-gram) + 向量两个通道同时打分，RRF 融合取 top_k。

    向量后端未装/未建库 → 该通道返回空 → 融合等价单通道，行为与现状一致（0 回归）。
    """
    pool = max(top_k * 2, _VEC_POOL)
    word_scored = _semantic_scored(root, query, top_k=pool, n=n, mode=mode)
    vec_scored = semantic_vector_retrieve(root, query, top_k=pool)
    return _rrf_fuse(word_scored, vec_scored, top_k)


def retrieve_with_meta(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> tuple[str, list[tuple[Card, float | None]]]:
    """混合检索入口，带通道与分数：返回 (channel, [(card, score|None)])

    channel: "empty"（空查询）| "deterministic"（确定性命中，score=None）| "semantic"
    """
    if not query.strip():
        return "empty", []
    hits = deterministic_retrieve(root, query, mode)
    if hits:
        return "deterministic", [(c, None) for c in hits]
    return "semantic", _fused_semantic(root, query, top_k, n, mode)


def retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """混合检索入口（兼容旧接口，仅返回卡片列表）

    n: 字符 n-gram 长度（char 模式），默认 2
    mode: "word"（默认，jieba 分词 + IDF）或 "char"（字符 n-gram，零依赖回退）
    """
    _, scored = retrieve_with_meta(root, query, top_k, n, mode)
    return [c for c, _ in scored]
