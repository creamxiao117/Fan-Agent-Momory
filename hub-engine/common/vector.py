"""轻量文本向量化：字符 n-gram / jieba 词袋 + 余弦相似度（jieba 为可选依赖）"""

import math
import re
from collections import Counter
from functools import lru_cache

_CHAR_RE = re.compile(r"\s+")

# 常用中文停用词（词模式去噪，保持精简）
STOPWORDS = frozenset(
    "的 了 在 是 我 你 他 她 它 与 和 并 就 都 要 把 被 对 从 到 会 能 可以 "
    "怎么 如何 一个 这个 那个 什么 哪些 这些 那些 进行 对于 以及 因为 所以 "
    "如果 但是 然后 或者 没有 不是 已经 之后 之前 现在 目前 需要 应该 比如 例如"
    .split()
)


def _has_jieba() -> bool:
    try:
        import jieba  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def _jieba():
    import jieba
    return jieba


def _is_punct(tok: str) -> bool:
    return all(
        not c.isalnum() and not ("\u4e00" <= c <= "\u9fff") for c in tok
    )


def tokenize(text: str, n: int = 2, mode: str = "char") -> list[str]:
    """归一化后切词。

    - char（默认）：字符 n-gram（零依赖，原行为）
    - word：jieba 分词 + 去停用词/标点；无 jieba 时自动回退 char 模式
    """
    if mode == "word" and _has_jieba():
        return [
            w
            for w in _jieba().lcut(text.lower())
            if w.strip() and not _is_punct(w) and w not in STOPWORDS
        ]
    norm = _CHAR_RE.sub(" ", text.lower())
    if len(norm) < n:
        return [norm] if norm else []
    return [norm[i : i + n] for i in range(len(norm) - n + 1)]


def build_idf(
    docs: list[str], n: int = 2, mode: str = "char"
) -> dict[str, float]:
    """语料文档 → 各 token 的 IDF 权重（平滑，避免除零）。"""
    df = Counter()
    for doc in docs:
        df.update(set(tokenize(doc, n, mode)))
    if not df:
        return {}
    doc_count = len(docs)
    return {
        tok: math.log((1 + doc_count) / (1 + df[tok])) + 1.0 for tok in df
    }


def vector(
    text: str, n: int = 2, mode: str = "char", idf: dict[str, float] | None = None
) -> Counter:
    """文本 → token 计数向量；传入 idf 时按权重加权。"""
    counts = Counter(tokenize(text, n, mode))
    if not idf:
        return counts
    default_w = 1.0
    return Counter(
        {tok: cnt * idf.get(tok, default_w) for tok, cnt in counts.items()}
    )


def cosine(a: Counter, b: Counter) -> float:
    """两个 Counter 的余弦相似度，0~1"""
    inter = sum(a[k] * b[k] for k in a.keys() & b.keys())
    la = math.sqrt(sum(v * v for v in a.values()))
    lb = math.sqrt(sum(v * v for v in b.values()))
    if not la or not lb:
        return 0.0
    return inter / (la * lb)
