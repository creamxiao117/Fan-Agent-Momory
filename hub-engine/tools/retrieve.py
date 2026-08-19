"""混合检索：确定性通道（按 type/tag 精确/词级命中）+ 语义通道（n-gram/分词 余弦召回）

第一层性能优化（2026-08-18）：进程内 `_CorpusIndex`
- 惰性扫描一次 active 卡，构建 type/tag 倒排索引（确定性通道 O(命中)）
- token counts 按 (path, mtime, size, mode, n) 缓存，jieba 分词只在卡片变更时重算
- 目录签名做失效校验：卡片增删改后自动重建索引，行为/顺序与逐次全扫完全一致
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
)


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
    scored = []
    for c in idx.cards:
        cv = idx.counts(c, mode, n)
        if idf:
            # 缓存的是未加权计数，这里按语料 IDF 统一加权后再比余弦
            cv = Counter({tok: cnt * idf.get(tok, 1.0) for tok, cnt in cv.items()})
        sim = cosine(qv, cv)
        if sim > 0:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(c, sim) for sim, c in scored[:top_k]]


def semantic_retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """语义通道：对 body+tags 做 token 余弦相似度召回 top-k（兼容旧接口）"""
    return [c for c, _ in _semantic_scored(root, query, top_k, n, mode)]


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
    return "semantic", _semantic_scored(root, query, top_k, n, mode)


def retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """混合检索入口（兼容旧接口，仅返回卡片列表）

    n: 字符 n-gram 长度（char 模式），默认 2
    mode: "word"（默认，jieba 分词 + IDF）或 "char"（字符 n-gram，零依赖回退）
    """
    _, scored = retrieve_with_meta(root, query, top_k, n, mode)
    return [c for c, _ in scored]
