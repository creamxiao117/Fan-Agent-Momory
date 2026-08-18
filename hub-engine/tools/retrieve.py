"""混合检索：确定性通道（按 type/tag 精确/词级命中）+ 语义通道（n-gram/分词 余弦召回）"""

from pathlib import Path

from common.frontmatter import Card, try_read_card
from common.vector import build_idf, cosine, tokenize, vector


def _walk_active_cards(root: Path) -> list[Card]:
    cards = []
    for sub in (
        "rules",
        "methodology",
        "longterm",
        "projects",
        "experience",
        "libs",
        "retro",
    ):
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            c = try_read_card(p)
            if c is not None and c.status != "archived":
                cards.append(c)
    return cards


def _card_text(c: Card) -> str:
    return c.body + " " + " ".join(c.tags)


def deterministic_retrieve(root: Path, query: str, mode: str = "word") -> list[Card]:
    """确定性通道：query 命中 type 或 tag 即返回。

    - char 模式：整句包含（原行为）
    - word 模式：额外支持词级匹配——query 任一分词与 tag 互相包含即命中
      （如查询含 "dll" 可命中 tag "dll-lock"，无需精确整句）
    """
    q = query.lower()
    q_words = tokenize(query, mode="word") if mode == "word" else []
    hits = []
    for c in _walk_active_cards(root):
        if q in c.type:
            hits.append(c)
            continue
        tags = [t.lower() for t in c.tags]
        if any(q in t for t in tags):
            hits.append(c)
            continue
        if q_words and any(any(w in t or t in w for w in q_words) for t in tags):
            hits.append(c)
    return hits


def semantic_retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """语义通道：对 body+tags 做 token 余弦相似度召回 top-k。

    - char：字符 n-gram（实测 n=2 最优）
    - word：jieba 分词 + IDF 加权（语料内稀有词权重更高，缓解领域共词抢占）
    """
    cards = _walk_active_cards(root)
    idf = (
        build_idf([_card_text(c) for c in cards], n=n, mode=mode)
        if mode == "word"
        else None
    )
    qv = vector(query, n=n, mode=mode, idf=idf)
    scored = []
    for c in cards:
        sim = cosine(qv, vector(_card_text(c), n=n, mode=mode, idf=idf))
        if sim > 0:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """混合检索入口：先确定性，命中即返回；否则语义召回

    n: 字符 n-gram 长度（char 模式），默认 2
    mode: "word"（默认，jieba 分词 + IDF）或 "char"（字符 n-gram，零依赖回退）
    """
    if not query.strip():
        return []  # 空查询护栏：避免空串命中全部卡片
    hits = deterministic_retrieve(root, query, mode)
    if hits:
        return hits
    return semantic_retrieve(root, query, top_k, n, mode)
