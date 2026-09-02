"""高频未命中查询补卡候选（建议 2）单测。

覆盖：零命中→P0 新增卡 / 低命中→P1 补tag / 高命中→ok / 忽略非 search 与空查询 / 归一化聚合。
"""

import json
from pathlib import Path

import pytest

from scripts.bootstrap_hub import bootstrap
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


# ---------- auto_apply_p1_tags（P1 执行端，2026-09-02 Hermes 补全） ----------


def _seed_card(root: Path, name: str, tags: list[str], body: str) -> Path:
    """在权威区 rules/ 种一张可被检索命中的卡（含 git 跟踪基线）。"""
    import subprocess

    p = root / "rules" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntype: rule\ntags: {tags}\nupdated: '2026-08-17'\n"
        f"status: active\nreuse_count: 0\n---\n{body}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root),
            "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "-m", "seed",
        ],
        check=True,
        capture_output=True,
    )
    return p


def _p1_log(root: Path, query: str, hits: list[int]) -> None:
    """按给定命中序列造 P1 日志（avg_hit<3 且非零命中主导）。"""
    _write_log(
        root,
        [
            _search(query, h, "deterministic" if i % 2 == 0 else "semantic")
            for i, h in enumerate(hits)
        ],
    )


def test_auto_apply_p1_tags_applies_and_is_idempotent(tmp_path):
    """P1 查询 → 目标卡 tags 追加；二跑幂等（不重复加、卡不变）。"""
    from common.frontmatter import read_card
    from scripts.missing_query import auto_apply_p1_tags

    root = bootstrap(tmp_path)
    card = _seed_card(
        root,
        "fuzzy-search-lock.md",
        ["检索"],
        "做模糊检索时先锁词库；查询模糊检索要检查分词与停用词。",
    )
    _p1_log(root, "模糊检索 优化", [1, 2, 1])

    r1 = auto_apply_p1_tags(root, root)
    assert r1["status"] == "ok"
    assert r1["applied_count"] == 1, r1
    assert r1["applied"][0]["tags_added"], "应产出 tags_added 非空"
    tags_after = read_card(card).tags
    assert "检索" in tags_after  # 原 tag 保留（无损）

    r2 = auto_apply_p1_tags(root, root)
    assert r2["applied_count"] == 0
    assert read_card(card).tags == tags_after  # 幂等：第二次不变更

    # git 回滚点：最后一次 commit 是本功能的提交
    import subprocess

    head = subprocess.run(
        ["git", "-C", str(root), "log", "--oneline", "-1"],
        capture_output=True, text=True,
    ).stdout
    assert "chore(p1-autotag)" in head


def test_auto_apply_p1_tags_respects_write_lock(tmp_path):
    """写锁被占时全部降级为 skipped，不写任何卡（与 ingest 互斥纪律）。"""
    from common.frontmatter import read_card
    from scripts.missing_query import auto_apply_p1_tags

    root = bootstrap(tmp_path)
    card = _seed_card(
        root,
        "fuzzy-search-lock.md",
        ["检索"],
        "做模糊检索时先锁词库。",
    )
    _p1_log(root, "模糊检索 优化", [1, 2, 1])

    lk = root / ".sync" / "locks" / "writer.lock"
    lk.parent.mkdir(parents=True, exist_ok=True)
    lk.write_text("")
    try:
        r = auto_apply_p1_tags(root, root)
        assert r["applied_count"] == 0
        assert r["skipped_count"] >= 1
        assert "写锁" in r["status"]
        assert read_card(card).tags == ["检索"]  # 卡未被触碰
    finally:
        lk.unlink()


def test_auto_apply_p1_tags_filters_low_freq(tmp_path):
    """不满足 count>=3 的 P1 候选不动手（保守门槛）。"""
    from common.frontmatter import read_card
    from scripts.missing_query import auto_apply_p1_tags

    root = bootstrap(tmp_path)
    card = _seed_card(root, "fuzzy-search-lock.md", ["检索"], "做模糊检索时先锁词库。")
    _p1_log(root, "模糊检索 优化", [1, 2])  # 仅 2 次，低于阈值

    r = auto_apply_p1_tags(root, root)
    assert r["applied_count"] == 0
    assert read_card(card).tags == ["检索"]


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


def test_aggregate_since_filters_outdated(tmp_path):
    """since 只保留该日期(含)之后的记录（A1 每日候选聚焦近期缺口）"""
    from datetime import date

    recs = [
        {**_search("缺口A", 0), "ts": "2026-08-10T02:00:00Z"},  # 旧，应排除
        {**_search("缺口A", 0), "ts": "2026-08-28T01:00:00Z"},  # +8 仍当日
        {**_search("缺口A", 0), "ts": "2026-08-19T05:00:00Z"},
    ]
    _write_log(tmp_path, recs)
    assert aggregate(tmp_path)[0]["count"] == 3  # 全历史含所有
    recent = aggregate(tmp_path, since=date(2026, 8, 19))
    assert recent[0]["count"] == 2  # 只保留当天


def test_main_since_days_ok(tmp_path, capsys):
    """CLI --since-days 接线正常，聚焦近期仍产出候选"""
    from scripts.missing_query import main

    _write_log(tmp_path, [{**_search("缺口A", 0), "ts": "2026-08-28T01:00:00Z"}])
    assert main(["--root", str(tmp_path), "--since-days", "7"]) == 0
    assert "缺口A" in capsys.readouterr().out
