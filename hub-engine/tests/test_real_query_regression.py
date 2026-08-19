"""E3 真实召回回归门禁（real_query_regression）单测。

覆盖：candidates 高频未命中 P0 过滤 / 固定集快照 构建·加载·老化·强制重建 /
gate_stats 聚合与全未命中 / gate_failed 默认与 --fail-below 阈值 / main 无可断言样本返回0。
命中判定注入 hit_fn，不依赖向量模型，保证确定性。
"""

import json
from datetime import date

from scripts.real_query_regression import (
    LOG,
    candidates,
    ensure_set,
    gate_failed,
    gate_stats,
    load_records,
    load_snapshot,
    persist_snapshot,
    snapshot_age_days,
)


def _write_log(root, records):
    p = root / LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _search(query, hit_count):
    return {
        "action": "search",
        "platform": "t",
        "query": query,
        "hit_count": hit_count,
    }


def test_load_records_empty_when_no_log(tmp_path):
    assert load_records(tmp_path) == []


def test_candidates_filters_p0_and_min_count(tmp_path):
    _write_log(
        tmp_path,
        [
            _search("DLL 并发锁", 0),
            _search("DLL 并发锁", 0),
            _search("DLL 并发锁", 0),  # P0：3 次全未命中
            _search("模糊检索", 1),  # 非 P0（有命中）
            _search("孤立话题", 0),  # 频次 1 < min_count=2
        ],
    )
    cands = candidates(tmp_path, min_count=2)
    assert [c["query"] for c in cands] == ["DLL 并发锁"]
    assert cands[0]["count"] == 3


def test_candidates_normalize_and_skip_non_search(tmp_path):
    _write_log(
        tmp_path,
        [
            {"action": "bootstrap", "platform": "t", "ok": True},
            _search("DLL Lock", 0),
            _search("  dll lock ", 0),  # 归一化合并为一条，频次2
        ],
    )
    cands = candidates(tmp_path, min_count=2)
    assert len(cands) == 1
    assert cands[0]["count"] == 2


def test_persist_and_load_snapshot_roundtrip(tmp_path):
    persist_snapshot(tmp_path, [{"query": "q1", "count": 3}], refreshed="2026-08-19")
    loaded = load_snapshot(tmp_path)
    assert loaded == [{"query": "q1", "count": 3}]
    assert snapshot_age_days(tmp_path, today=date(2026, 8, 20)) == 1


def test_ensure_set_builds_when_missing(tmp_path):
    _write_log(tmp_path, [_search("缺失话题", 0), _search("缺失话题", 0)])
    items, from_log = ensure_set(
        tmp_path, min_count=2, max_age_days=7, force_refresh=False
    )
    assert from_log is True
    assert [i["query"] for i in items] == ["缺失话题"]


def test_ensure_set_uses_cache_when_fresh(tmp_path):
    persist_snapshot(
        tmp_path, [{"query": "旧样本", "count": 2}], refreshed="2026-08-19"
    )
    # 日志与快照不一致——但快照仍新，不应重建（固定集稳定）
    _write_log(tmp_path, [_search("新样本", 0), _search("新样本", 0)])
    items, from_log = ensure_set(
        tmp_path,
        min_count=2,
        max_age_days=7,
        force_refresh=False,
        today=date(2026, 8, 20),
    )
    assert from_log is False  # 快照仍新 → 用缓存
    assert [i["query"] for i in items] == ["旧样本"]


def test_ensure_set_rebuilds_when_stale(tmp_path):
    persist_snapshot(
        tmp_path, [{"query": "旧样本", "count": 2}], refreshed="2026-08-10"
    )
    _write_log(tmp_path, [_search("新样本", 0), _search("新样本", 0)])
    items, from_log = ensure_set(
        tmp_path,
        min_count=2,
        max_age_days=7,
        force_refresh=False,
        today=date(2026, 8, 20),
    )
    assert from_log is True  # 龄 10 天 >= 7 → 重建
    assert [i["query"] for i in items] == ["新样本"]


def test_ensure_set_force_refresh_rebuilds(tmp_path):
    persist_snapshot(
        tmp_path, [{"query": "旧样本", "count": 2}], refreshed="2026-08-19"
    )
    _write_log(tmp_path, [_search("新样本", 0), _search("新样本", 0)])
    items, from_log = ensure_set(
        tmp_path,
        min_count=2,
        max_age_days=7,
        force_refresh=True,
        today=date(2026, 8, 20),
    )
    assert from_log is True
    assert [i["query"] for i in items] == ["新样本"]


def test_gate_stats_and_default_all_miss_fails():
    items = [{"query": "q1", "count": 2}, {"query": "q2", "count": 2}]

    def always_miss(q):
        return False

    stats = gate_stats(items, always_miss)
    assert stats["total"] == 2
    assert stats["hits"] == 0
    assert stats["hit_ratio"] == 0.0
    assert set(stats["miss_queries"]) == {"q1", "q2"}
    assert gate_failed(stats["hit_ratio"], None) is True  # 全未命中即 fail


def test_gate_stats_partial_hit_passes_default():
    items = [{"query": "q1", "count": 2}, {"query": "q2", "count": 2}]

    def hit_first(q):
        return q == "q1"

    stats = gate_stats(items, hit_first)
    assert stats["hits"] == 1
    assert stats["hit_ratio"] == 0.5
    assert gate_failed(stats["hit_ratio"], None) is False  # 非全未命中 → 默认通过


def test_gate_failed_threshold_value():
    assert gate_failed(0.4, 0.5) is True  # 低于阈值 fail
    assert gate_failed(0.5, 0.5) is False  # 等于阈值通过
    assert gate_failed(0.6, 0.5) is False
    assert gate_failed(0.0, None) is True  # 默认：全未命中
    assert gate_failed(0.0, 0.5) is True
    assert gate_failed(None, None) is True  # 防御


def test_main_no_assertion_samples_returns_zero(tmp_path):
    # 无 P0 样本 → 返回 0（正常跳过），不触碰检索模型
    _write_log(tmp_path, [_search("已命中话题", 5)])
    from scripts.real_query_regression import main

    assert main(["--root", str(tmp_path)]) == 0
