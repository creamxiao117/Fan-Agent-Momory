"""snippet：从卡片正文抽取与 query 最相关的片段节选（纯展示层，不参与检索）。

对齐 md-GuanLi「命中返回相关段落 snippet」的给答案方式：
抓取正文中与查询词重叠最多的行及其上下文，而非简单取卡片前 N 字。
无有效查询词 / 无命中行 → 回退取正文开头，行为不劣于旧版 excerpt。
"""

from common.vector import tokenize
from tools.retrieve import _EN_STOP

_DEFAULT_LIMIT = 200


def _query_words(query: str, mode: str = "word") -> list[str]:
    """分词并过滤弱词（单字符 + 英文功能词），无有效词返回空 → 触发回退。"""
    if not query.strip():
        return []
    return [w for w in tokenize(query, mode=mode) if len(w) >= 2 and w not in _EN_STOP]


def extract_snippet(body: str, query: str, limit: int = _DEFAULT_LIMIT) -> str:
    """正文 → 与 query 最相关片段（含前后一行上下文），超长截断加省略号。"""
    if not body:
        return ""
    words = _query_words(query)
    if not words:
        return body[:limit]

    lines = body.splitlines() or [""]
    scores = [sum(1 for w in words if w in ln.lower()) for ln in lines]
    best = max(scores)
    if best <= 0:
        return body[:limit]

    i = scores.index(best)
    seg = "\n".join(lines[max(0, i - 1) : min(len(lines), i + 2)])
    if len(seg) <= limit:
        return seg
    return seg[: limit - 1] + "…"
