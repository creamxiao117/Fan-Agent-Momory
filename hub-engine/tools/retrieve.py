"""混合检索：确定性通道（按 type/tag 精确命中）+ 语义通道（n-gram 余弦召回）"""
from pathlib import Path

from common.frontmatter import Card, read_card
from common.vector import cosine, vector


def _walk_active_cards(root: Path) -> list[Card]:
    cards = []
    for sub in ("rules", "experience", "projects", "libs", "retro"):
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                c = read_card(p)
            except Exception:
                continue
            if c.status != "archived":
                cards.append(c)
    return cards


def deterministic_retrieve(root: Path, query: str) -> list[Card]:
    """确定性通道：query 命中 type 或任一 tag 即返回"""
    q = query.lower()
    return [c for c in _walk_active_cards(root)
            if q in c.type or any(q in t.lower() for t in c.tags)]


def semantic_retrieve(root: Path, query: str, top_k: int = 5) -> list[Card]:
    """语义通道：对 body+tags 做 n-gram 余弦相似度召回 top-k"""
    qv = vector(query)
    scored = []
    for c in _walk_active_cards(root):
        sim = cosine(qv, vector(c.body + " " + " ".join(c.tags)))
        if sim > 0:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def retrieve(root: Path, query: str, top_k: int = 5) -> list[Card]:
    """混合检索入口：先确定性，命中即返回；否则语义召回（网关不可用时的兜底方案）"""
    if not query.strip():
        return []  # 空查询护栏：避免空串命中全部卡片
    hits = deterministic_retrieve(root, query)
    if hits:
        return hits
    return semantic_retrieve(root, query, top_k)
