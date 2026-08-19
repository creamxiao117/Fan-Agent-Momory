"""高频未命中查询补卡候选（建议 2）单测。

覆盖：零命中→P0 新增卡 / 低命中→P1 补tag / 高命中→ok / 忽略非 search 与空查询 / 归一化聚合。
"""

import json

import pytest
from scripts.missing_query import LOG, aggregate, to_markdown


def _write_log(root, records):
    p = root / LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8"
    )


def _search(query, hit_count, channel="semantic"):
    return {
        "ts": "t",
        "action": "search",
        "platform": "test",
        "ok": True,
        "query": query,
        "channel": channel,
        "hit_count": hit_count,
    }


def _stage_map(cands):
    return {c["query"]: c["stage"] for c in cands}


def test_zero_hit_high_freq_is_p0(tmp_path):
    """多次零命中的查询 → P0 新增卡片"""
    recs = [_search("DLL 并发锁", 0) for _ in range(3)]
    _write_log(tmp_path, recs)
    cands = aggregate(tmp_path)
    assert len(cands) == 1
    assert cands[0]["stage"] == "P0-新增卡片"
    assert cands[0]["count"] == 3
    assert cands[0]["zero_ratio"] == 1.0


def test_low_hit_is_p1(tmp_path):
    """有命中但平均命中少（未成零命中主导）→ P1 补 tag/别名"""
    _write_log(
        tmp_path,
        [
            _search("模糊检索", 1, "deterministic"),
            _search("模糊检索", 2, "semantic"),
            _search("模糊检索", 1, "semantic"),
        ],
    )
    cands = aggregate(tmp_path)
    assert len(cands) == 1
    assert cands[0]["stage"] == "P1-补tag别名"
    assert cands[0]["avg_hit"] == pytest.approx(4 / 3, abs=0.01)


def test_ok_hit_not_listed_as_gap(tmp_path):
    """高且稳定命中 → ok-无需处理（仍出现在清单但标 ok）"""
    _write_log(tmp_path, [_search("DLL 版本防锁", 5) for _ in range(2)])
    cands = aggregate(tmp_path)
    assert cands[0]["stage"] == "ok-无需处理"


def test_ignores_non_search_and_empty(tmp_path):
    """非 search 事件、空查询不计入候选"""
    recs = [
        {"action": "bootstrap", "platform": "t", "task_kind": "x", "ok": True},
        {"action": "search", "platform": "t", "query": "", "hit_count": 0},
        {"action": "search", "platform": "t", "query": "   ", "hit_count": 0},
        _search("真实缺陷", 0),
    ]
    _write_log(tmp_path, recs)
    cands = aggregate(tmp_path)
    assert len(cands) == 1
    assert cands[0]["query"] == "真实缺陷"


def test_normalize_whitespace_case(tmp_path):
    """查询归一化：首尾空白、大小写归并成一条"""
    _write_log(
        tmp_path,
        [_search("DLL Lock", 0), _search("  dll lock ", 0)],
    )
    cands = aggregate(tmp_path)
    assert len(cands) == 1
    assert cands[0]["count"] == 2


def test_markdown_includes_p0_and_p1(tmp_path):
    """Markdown 渲染含 P0/P1 两分区"""
    _write_log(tmp_path, [_search("缺口A", 0), _search("独立查询B", 1)])
    md = to_markdown(aggregate(tmp_path))
    assert "P0" in md and "P1" in md