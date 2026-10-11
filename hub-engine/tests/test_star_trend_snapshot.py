# @version V1.0 / 2026-10-10 / pi / 涨星第二源（自建 star 快照账本）单测
"""`scripts.star_trend_snapshot` 单测：delta 口径、账本幂等、Trending 解析。

不触网：`fetch_*` 一律不调用；`parse_trending` 用小段 HTML 夹具。
"""

from __future__ import annotations

from pathlib import Path

from scripts.star_trend_snapshot import (
    delta,
    main,
    parse_trending,
    read_ledger,
    record,
)


def _rec(day: str, slug: str, stars: int) -> dict:
    return {"day": day, "slug": slug, "stars": stars, "source": "gh-api"}


# ---------- 账本读写 / 幂等 ----------


def test_record_roundtrip_and_idempotent(tmp_path: Path):
    ledger = tmp_path / "star-trend.jsonl"
    assert record(ledger, "a/b", 100, day="2026-10-01") is True
    assert record(ledger, "a/b", 100, day="2026-10-01") is False, "同键同值不该重写"
    assert record(ledger, "a/b", 150, day="2026-10-01") is True, "同键异值应覆盖（JIT/重跑不污染）"
    recs = read_ledger(ledger)
    assert len(recs) == 1 and recs[0]["stars"] == 150


def test_read_ledger_skips_bad_lines(tmp_path: Path):
    ledger = tmp_path / "star-trend.jsonl"
    ledger.write_text(
        '{"day": "2026-10-01", "slug": "a/b", "stars": 1}\n'
        "这不是 JSON\n"
        '{"day": "2026-10-02"}\n'  # 缺 slug
        '{"day": "2026-10-03", "slug": "c/d", "stars": 3}\n',
        encoding="utf-8",
    )
    assert [r["slug"] for r in read_ledger(ledger)] == ["a/b", "c/d"]


# ---------- delta 口径 ----------


def test_delta_measured_when_history_covers_window():
    recs = [_rec("2026-09-26", "a/b", 1000), _rec("2026-10-10", "a/b", 1234)]
    d = delta(recs, "a/b", days=14, today="2026-10-10")
    assert d is not None
    assert d["delta"] == 234 and d["span_days"] == 14
    assert d["evidence"] == "measured", d


def test_delta_partial_when_history_shorter_than_window():
    """跨度不足时必须标 measured-partial（数字真实但**不是** 2 周口径）。"""
    recs = [_rec("2026-10-05", "a/b", 1000), _rec("2026-10-10", "a/b", 1100)]
    d = delta(recs, "a/b", days=14, today="2026-10-10")
    assert d is not None and d["evidence"] == "measured-partial" and d["span_days"] == 5


def test_delta_none_cases():
    assert delta([], "a/b", today="2026-10-10") is None, "无记录 → None（调用方退化为 claim）"
    assert delta([_rec("2026-10-10", "a/b", 1)], "a/b", today="2026-10-10") is None, "只有一天 → 涨星无从谈起"
    assert delta([_rec("2026-10-10", "other/repo", 1)], "a/b", today="2026-10-10") is None, "只看本仓"


def test_delta_ignores_future_records():
    """账本里若有“未来”日期（时钟漂移），不能被当成 now 基准。"""
    recs = [_rec("2026-09-26", "a/b", 100), _rec("2026-12-31", "a/b", 999)]
    d = delta(recs, "a/b", days=14, today="2026-10-10")
    assert d is None or d["day_now"] <= "2026-10-10"


# ---------- Trending 解析 ----------


def test_parse_trending_extracts_slugs_in_order():
    html = (
        '<a href="/sponsors/x">sp</a>'
        '<a href="/mvschwarz/openrig">openrig</a>'
        '<a href="/trending/daily">nav</a>'
        '<a href="/heygen-com/hyperframes">hf</a>'
        '<a href="/mvschwarz/openrig">dupe</a>'
    )
    assert parse_trending(html) == ["mvschwarz/openrig", "heygen-com/hyperframes"]


def test_parse_trending_empty_on_garbage():
    assert parse_trending("") == []
    assert parse_trending("<html>no repos here</html>") == []


# ---------- CLI ----------


def test_cli_query_without_history_exits_2(tmp_path: Path, capsys):
    """无历史 → exit 2 + 明确提示“退化为 claim”（这是**预期信号**，不是错误）。"""
    rc = main(["--hub", str(tmp_path), "query", "--slug", "a/b", "--days", "14"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "claim" in out


def test_cli_query_json_measured(tmp_path: Path):
    ledger = tmp_path / "system" / "run" / "star-trend.jsonl"
    record(ledger, "a/b", 100, day="2026-09-28")
    record(ledger, "a/b", 300, day="2026-10-10")
    rc = main(["--hub", str(tmp_path), "query", "--slug", "a/b", "--days", "14", "--json"])
    assert rc == 0, "跨度 ≥ 14 天应给 measured（exit 0）"
