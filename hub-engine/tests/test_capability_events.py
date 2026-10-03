"""能力使用登记台账（(a) 技能使用登记）单测。

背景：2026-10-03 要"删掉没用过的客户端技能"时发现**根本没有使用遥测**
（route_trace/reuse_daily 记的是中枢卡片，不是客户端技能）。没有登记就谈不上"没使用过"。
"""

from __future__ import annotations

from pathlib import Path

from common.capability_events import (
    never_recorded,
    record,
    record_many,
    rows,
    stats,
    summarize,
)


def test_append_only_and_read_back(tmp_path: Path):
    assert record(tmp_path, "injected", "alpha", platform="pi", source="tier_bootstrap")
    assert record(tmp_path, "suggested", "beta", platform="pi")
    rs = rows(tmp_path)
    assert [r["name"] for r in rs] == ["alpha", "beta"]
    assert rs[0]["event"] == "injected"


def test_illegal_event_is_dropped_not_raised(tmp_path: Path):
    """非法事件静默丢弃（登记是旁路，不能因它让主流程失败）。"""
    assert record(tmp_path, "frobnicate", "alpha") is False
    assert record(tmp_path, "injected", "") is False
    assert rows(tmp_path) == []


def test_never_raises_on_unwritable_path(tmp_path: Path):
    """路径不可写时返回 False，**不抛异常**（旁路纪律）。"""
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x", encoding="utf-8")
    assert record(blocked / "sub", "injected", "alpha") is False


def test_summarize_counts_and_never_recorded(tmp_path: Path):
    for _ in range(3):
        record(tmp_path, "injected", "alpha", platform="pi")
    record(tmp_path, "suggested", "alpha", platform="pi")
    agg = summarize(tmp_path, days=30)
    assert agg["alpha"]["counts"] == {"injected": 3, "suggested": 1}
    assert agg["alpha"]["platforms"] == ["pi"]
    # "没使用过"的唯一可证明形式：台账里一条都没有
    assert never_recorded(tmp_path, ["alpha", "beta"]) == ["beta"]


def test_record_many_batches(tmp_path: Path):
    n = record_many(tmp_path, "injected", ["a", "b", "c"], platform="workbuddy")
    assert n == 3
    assert stats(tmp_path)["events"]["injected"] == 3


def test_summarize_respects_window(tmp_path: Path):
    """窗口过滤：老事件不该算进"最近用过"。"""
    record(tmp_path, "injected", "old")
    p = tmp_path / ".sync/state/capability_events.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace("20", "19", 1), encoding="utf-8")
    assert summarize(tmp_path, days=30) == {} or "old" not in summarize(tmp_path, days=30)
