"""轻量文本向量化：字符 n-gram 词袋 + 余弦相似度（零外部依赖）"""
import math
import re
from collections import Counter


def tokenize(text: str, n: int = 2) -> list[str]:
    """归一化后切字符 n-gram"""
    norm = re.sub(r"\s+", " ", text.lower())
    if len(norm) < n:
        return [norm] if norm else []
    return [norm[i:i + n] for i in range(len(norm) - n + 1)]


def vector(text: str, n: int = 2) -> Counter:
    """文本 → 字符 n-gram 计数向量"""
    return Counter(tokenize(text, n))


def cosine(a: Counter, b: Counter) -> float:
    """两个 Counter 的余弦相似度，0~1"""
    inter = sum(a[k] * b[k] for k in a.keys() & b.keys())
    la = math.sqrt(sum(v * v for v in a.values()))
    lb = math.sqrt(sum(v * v for v in b.values()))
    if not la or not lb:
        return 0.0
    return inter / (la * lb)
