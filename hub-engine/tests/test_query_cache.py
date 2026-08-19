"""查询侧 embedding LRU 缓存（建议 1）单测。

验证：同 query 复用免重复推理 / LRU 超限淘汰最老 / 退化(None)不缓存 / 空查询不触发。
用计数 fake embed 替换后端，不加载真实模型/不联网。
"""

from tools.semsearch import clear_query_cache, query_embedded, set_embed_backend


class _CountingEmbed:
    """计数 embed：记录调用次数，可配置返回 None 模拟后端退化。"""

    def __init__(self):
        self.calls: list[str] = []
        self.degraded = False

    def __call__(self, text: str):
        self.calls.append(text)
        if self.degraded:
            return None
        return [float(len(text)), 1.0]


def test_same_query_embeds_once(tmp_path):
    """同 query 第二次走缓存，embed 不重复调用"""
    set_embed_backend(None)  # 复位为默认真实后端前先注入 fake（避免真实模型被触发）
    emb = _CountingEmbed()
    set_embed_backend(emb)
    clear_query_cache()
    try:
        q = "DLL 修改后必须递增版本号"
        v1 = query_embedded(q)
        v2 = query_embedded(q)
        v3 = query_embedded(q)
        assert v1 == v2 == v3 is not None
        assert emb.calls == [q], f"应只推理一次，实际 {emb.calls}"
    finally:
        set_embed_backend(None)
        clear_query_cache()


def test_distinct_queries_independent(tmp_path):
    """不同 query 互不干扰，各推理一次"""
    emb = _CountingEmbed()
    set_embed_backend(emb)
    clear_query_cache()
    try:
        qa, qb = "检索召回率", "DLL 防锁"
        va, vb = query_embedded(qa), query_embedded(qb)
        query_embedded(qa)  # 命中缓存
        assert va is not None and vb is not None
        assert set(emb.calls) == {qa, qb}
    finally:
        set_embed_backend(None)
        clear_query_cache()


def test_lru_evicts_oldest(tmp_path):
    """超限淘汰最早插入项：先塞满至上限，最近使用的驻留、最早的被逐出"""
    emb = _CountingEmbed()
    set_embed_backend(emb)
    clear_query_cache()
    try:
        limit = _query_cache_limit()
        queries = [f"query-{i}" for i in range(limit)]
        for i, q in enumerate(queries):
            query_embedded(q)
            if i >= limit - 2:  # 预留 early 触发
                pass
        # 再插入一条超限 → 最老的 query-0 被淘汰
        query_embedded("query-last")
        assert query_embedded("query-0")  # 重新演算，返回非 None 即视为被逐出
        assert emb.calls.count("query-0") == 2, "query-0 应被淘汰后重算一次"
        # 最近使用的 query-last 应命中缓存，不再推理
        c_before = len(emb.calls)
        query_embedded("query-last")
        assert len(emb.calls) == c_before
    finally:
        set_embed_backend(None)
        clear_query_cache()


def test_degraded_none_not_cached(tmp_path):
    """embed 返回 None（后端退化）时不缓存；后端恢复后能正常命中"""
    emb = _CountingEmbed()
    set_embed_backend(emb)
    clear_query_cache()
    try:
        q = "退化查询"
        emb.degraded = True
        assert query_embedded(q) is None  # 退化，不缓存
        emb.degraded = False
        assert query_embedded(q) is not None  # 恢复后正常推理并缓存
        c = len(emb.calls)
        assert query_embedded(q) is not None  # 命中缓存，不再推理
        assert len(emb.calls) == c
    finally:
        set_embed_backend(None)
        clear_query_cache()


def test_empty_query_no_embed(tmp_path):
    """空查询不触发 embedding 也不进缓存"""
    emb = _CountingEmbed()
    set_embed_backend(emb)
    clear_query_cache()
    try:
        assert query_embedded("") is None
        assert query_embedded("   ") is not None  # 非空（含空白）仍处理
        assert emb.calls == ["   "]
    finally:
        set_embed_backend(None)
        clear_query_cache()


def _query_cache_limit():
    """从 semsearch 取模块级 LRU 上限（避免测试硬编码漂移）"""
    from tools import semsearch

    return semsearch._QUERY_CACHE_LIMIT
