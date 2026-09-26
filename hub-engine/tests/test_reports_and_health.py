# @version V1.0 / 2026-09-25 / COV：日报/健康/运行日志三个 0% 脚本的覆盖面
"""`hub_daily_report` · `hub_health` · `flywheel_runlog` 的行为测试。

## 为什么补这三个

COV 任务：`scripts/` 覆盖率 26.9% → ≥40%。这三个脚本在覆盖率报告里是 **0%**
且语句数最大（275 / 265 / 201），但它们绝大多数是**纯格式化与统计逻辑**，
用 fixture 就能真跑，不需要 mock，性价比最高。

覆盖到的关键口径（都是容易静默错的地方）：
- 知识缺口：只统计窗口内的 `search`/`retrieve`，`hit_count==0` 才算 miss
- 飞轮活跃度：**无日志必须是 available=False，而不是冒充 0 分**（旧实现恒 0 造成假告警）
- 健康分加权：不可用分项要**从权重中剔除**，不能按 0 计入
- runlog：input/output 截断上限（500/1000）与 `group_by_run` 的组头规则
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from scripts import flywheel_runlog as frl
from scripts import hub_daily_report as hdr
from scripts import hub_health as hh
from scripts.bootstrap_hub import bootstrap

# ---------------------------------------------------------------------------
# hub_daily_report：知识缺口
# ---------------------------------------------------------------------------


def test_detect_knowledge_gaps_missing_log(tmp_path):
    gap = hdr.detect_knowledge_gaps(tmp_path / "nope.jsonl")
    assert gap["error"] == "log not found"
    assert gap["total"] == 0 and gap["miss_rate"] == 0.0


def test_detect_knowledge_gaps_window_and_miss_rules(tmp_path):
    """只统计窗口内的 search/retrieve；hit_count==0 才算 miss；坏行跳过。"""
    log = tmp_path / "query.log.jsonl"
    now = time.time()
    old = now - 10 * 24 * 3600
    rows = [
        {"ts": now, "action": "search", "hit_count": 0, "query": "缺卡查询"},
        {"ts": now, "action": "retrieve", "hit_count": 3, "query": "命中查询"},
        {"ts": now, "action": "search", "hit_count": 0, "query": "缺卡查询"},
        {"ts": now, "action": "ingest", "hit_count": 0, "query": "非检索动作"},
        {"ts": old, "action": "search", "hit_count": 0, "query": "窗口外"},
        {"ts": "不是数字", "action": "search", "hit_count": 0, "query": "坏时间戳"},
        {"ts": now, "action": "search", "hit_count": 0, "query": "   "},
    ]
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n不是 json\n", encoding="utf-8")

    gap = hdr.detect_knowledge_gaps(log, window_hours=24)

    assert gap["total"] == 4, "窗口内 4 条检索动作（含空 query 那条：它计入分母）"
    assert gap["miss"] == 3, "其中 3 条 hit_count==0"
    assert gap["miss_rate"] == round(3 / 4 * 100, 1)
    assert gap["top_misses"][0] == ("缺卡查询", 2), "空 query 不进高频榜"


# ---------------------------------------------------------------------------
# hub_daily_report：6 面板与格式化
# ---------------------------------------------------------------------------


def test_load_6panel_three_states(tmp_path):
    hub = tmp_path / "hub"
    (hub / "system" / "run").mkdir(parents=True)
    assert hdr._load_6panel(hub) is None  # 未跑

    p = hub / "system" / "run" / "daily-6panel.json"
    p.write_text("{坏 json", encoding="utf-8")
    assert "_error" in hdr._load_6panel(hub)

    p.write_text(json.dumps({"results": {"skill_health": {"ok": True}}}), encoding="utf-8")
    assert hdr._load_6panel(hub)["results"]["skill_health"]["ok"] is True


def test_format_6panel_section_variants():
    assert hdr._format_6panel_section(None) == []
    assert hdr._format_6panel_section({}) == []
    assert hdr._format_6panel_section({"results": {}}) == []
    err = hdr._format_6panel_section({"_error": "读不动"})
    assert err and "不可读" in err[0]

    panel = {
        "results": {
            "skill_health": {"ok": True, "info": {"stdout": "avg: 95.0 low_health: 0"}},
            "llm_route": {"ok": True, "info": {"stdout": "llm_route hits: []"}},
            "stale_detect": {"ok": True, "info": {"stdout": "Stale 卡片：0 张\nStale 技能：0 个"}},
            "knowledge_gap": {"ok": True, "info": {"stdout": "gap: 0/0 (0.0%)"}},
            "skill_candidate": {"ok": False, "info": {"stdout": ""}},
        }
    }
    lines = hdr._format_6panel_section(panel)
    joined = "\n".join(lines)
    assert "avg: 95.0" in joined
    assert "fallback 可用但 LLM 决策无命中" in joined  # hits: [] 的特殊文案
    assert "Stale 卡片：0 张" in joined
    assert "gap: 0/0" in joined


def test_time_and_score_helpers():
    assert hdr._local_now_iso("2026-09-25T00:00:00+00:00") == "2026-09-25 08:00"
    assert hdr._local_now_iso("不是时间") == "不是时间"
    assert hdr._local_now_iso("") == "未知"
    assert hdr._score_bar(0) == "░" * 8
    assert hdr._score_bar(100) == "█" * 8
    assert hdr._score_bar(50, width=4) == "██░░"
    assert [hdr._verdict(s) for s in (90, 72, 60, 40, 10)] == [
        "优秀",
        "良好",
        "需关注",
        "偏弱",
        "告急",
    ]


def test_format_report_renders_full_snapshot():
    data = {
        "generated_at": "2026-09-25T00:00:00+00:00",
        "period_days": 7,
        "health_scores": {
            "overall": 92.0,
            "card_health": 100.0,
            "skill_health": 95.0,
            "flywheel_activity": 100.0,
            "llm_health": 60.0,
        },
        "card_stats": {
            "total": 469,
            "by_status": {"active": 300, "archived": 8, "candidate": 50, "reference": 73},
            "by_type": {"exp": 224, "methodology": 61, "rule": 35},
        },
        "flywheel_stats": {"run": 3, "flywheel": 2, "register": 1, "smoke": 0},
        "skill_stats": {"total": 12, "by_status": {"active": 10}},
        "llm_status": {"available": True, "models": ["qwen3.8-27b-fast"], "response_time": 1.2},
        "alerts": [{"level": "info", "rule": "local_llm_slow", "message": "本地 LLM 响应慢"}],
        "_6panel": {"results": {"skill_health": {"ok": True, "info": {"stdout": "avg: 95.0 low_health: 0"}}}},
        "_gap": {"total": 3, "miss": 2, "miss_rate": 66.7, "top_misses": [("缺卡查询", 2)]},
    }
    text = hdr.format_report(data)
    assert "记忆中枢飞轮日报" in text
    assert "92" in text and "优秀" in text
    assert "469" in text
    assert "avg: 95.0" in text  # 6 面板段落
    assert "缺卡查询" in text  # 缺口段落
    assert "本地 LLM 响应慢" in text  # 告警段落


def test_format_report_survives_empty_data():
    """空数据不得崩（首日/未跑巡检时的常见输入）。

    回归：2026-09-25 COV 实测 `format_report({})` 曾因 `_gap` 缺失而 KeyError。
    """
    text = hdr.format_report({})
    assert "记忆中枢飞轮日报" in text
    assert "无飞轮运行记录" in text, "空飞轮统计应走兜底文案"


# ---------------------------------------------------------------------------
# hub_health：采集与评分
# ---------------------------------------------------------------------------


def test_count_files_by_pattern_window(tmp_path):
    (tmp_path / "recent.md").write_text("x", encoding="utf-8")
    old = tmp_path / "old.md"
    old.write_text("x", encoding="utf-8")
    old_ts = time.time() - 30 * 24 * 3600
    os.utime(old, (old_ts, old_ts))

    got = hh.count_files_by_pattern(tmp_path, "*.md", days=7)
    assert got["total"] == 1, "窗口外的不计入"
    assert sum(got["by_day"].values()) == 1


def test_count_scripts_run_counts_logs(tmp_path):
    """阶段脚本名来自 FLYWHEEL_STAGES（如 hub-ingest.py），按 `<script>*.log` 计数。"""
    (tmp_path / "hub-ingest.py-1.log").write_text("x", encoding="utf-8")
    (tmp_path / "hub-lint.py-2.log").write_text("x", encoding="utf-8")
    (tmp_path / "query.log").write_text(
        f"{datetime.now(tz=timezone.utc).isoformat()} | hub-dedup.py 调用\n", encoding="utf-8"
    )
    stats = hh.count_scripts_run(tmp_path, days=7)
    assert set(stats) == set(hh.FLYWHEEL_STAGES)
    assert stats["ingest"] == 1 and stats["lint"] == 1
    assert stats["dedup"] == 1, "query.log 里的调用也计入"


def test_collect_card_stats_on_bootstrapped_hub(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "r1.md").write_text(
        "---\ntype: rule\ntags: [t]\nupdated: '2026-09-25'\nstatus: active\n---\n正文\n",
        encoding="utf-8",
    )
    stats = hh.collect_card_stats(root)
    assert stats["total"] >= 1
    assert {"by_type", "by_status", "cards"} <= set(stats)
    assert stats["by_type"].get("rule", 0) >= 1


def test_collect_flywheel_activity_unavailable_is_not_zero(tmp_path):
    """无日志 → available=False（**不冒充 0 分**，否则会出现假告警）。"""
    act = hh.collect_flywheel_activity(tmp_path)
    assert act["available"] is False
    assert act["score"] is None


def test_collect_flywheel_activity_scores_today_as_full(tmp_path):
    state = tmp_path / ".sync" / "state"
    state.mkdir(parents=True)
    today = datetime.now(tz=timezone.utc).date().isoformat()
    (state / "flywheel-log.json").write_text(json.dumps([{"date": today}, {"date": today}]), encoding="utf-8")
    act = hh.collect_flywheel_activity(tmp_path)
    assert act["available"] is True
    assert act["days_since_last"] == 0 and act["score"] == 100.0
    assert act["runs_in_window"] == 1  # runs_in_window 数的是**天数**


def test_compute_health_score_shape_and_weighting():
    card_stats = {"total": 10, "by_status": {"active": 8, "archived": 1}, "by_type": {"rule": 5}}
    skill_stats = {"total": 4, "by_status": {"active": 3}}
    flywheel_stats = {"run": 2, "flywheel": 2, "register": 1, "smoke": 0}
    activity = {"available": True, "score": 100.0, "days_since_last": 0, "runs_in_window": 1}

    scores = hh.compute_health_score(card_stats, skill_stats, flywheel_stats, None, activity)
    assert 0 <= scores["overall"] <= 100
    for key in ("card_health", "skill_health", "flywheel_activity"):
        assert key in scores
    # 2026-09-25 修正：LLM 状态未提供 ⇒ None（从权重剔除），不再默认满分 100
    assert scores["llm_health"] is None
    assert scores["_weight_available"] == 0.8, "llm 权重 0.2 应被剔除"


def test_compute_health_score_tolerates_incomplete_stats():
    """残缺统计不得崩（回归：原先 card_stats['total'] 直取会 KeyError）。"""
    scores = hh.compute_health_score({}, {}, {})
    assert scores["card_health"] is None and scores["skill_health"] is None
    assert scores["flywheel_activity"] is None, "无活动证据 ⇒ None，不冒充 0"


def test_check_alerts_rules_and_clean_case(tmp_path):
    hub = bootstrap(tmp_path)
    skillhub = tmp_path / "skillhub"
    skillhub.mkdir()
    card_stats = {"total": 5, "by_status": {"active": 5}, "by_type": {"rule": 5}}
    flywheel_stats = {"run": 1}
    activity = {"available": True, "score": 100.0}

    # 干净场景：无告警
    assert hh.check_alerts(hub, skillhub, card_stats, {"total": 0}, flywheel_stats) == []

    # 规则 1：连续 N 天无新产物（把最近一次运行推到很久以前）
    state = hub / ".sync" / "state"
    state.mkdir(parents=True, exist_ok=True)
    old_day = (datetime.now(tz=timezone.utc) - timedelta(days=30)).date().isoformat()
    (state / "flywheel-log.json").write_text(json.dumps([{"date": old_day}]), encoding="utf-8")
    alerts = hh.check_alerts(hub, skillhub, card_stats, {"total": 0}, flywheel_stats, alert_days=2)
    assert alerts, "旧日志应触发『连续无产物』类告警"
    assert {"level", "rule", "message"} <= set(alerts[0])
    assert activity["score"] == 100.0  # 形参 activity 不参与，仅确保调用签名兼容


# ---------------------------------------------------------------------------
# flywheel_runlog：记录与时间线
# ---------------------------------------------------------------------------


def test_append_and_load_records_roundtrip(tmp_path):
    sh = tmp_path / "skillhub"
    rec1 = frl.make_record("run", "in1", "out1", True, {"run_id": "r1"})
    rec2 = frl.make_record("flywheel", "in2", "out2", False)
    frl.append_record(sh, rec1)
    frl.append_record(sh, rec2)

    rows = frl.load_records(sh)
    assert [r["stage"] for r in rows] == ["run", "flywheel"]
    assert rows[0]["run_id"] == "r1"
    assert len(frl.load_records(sh, limit=1)) == 1
    assert frl.runlog_path(sh).is_file()


def test_make_record_truncates_and_labels():
    rec = frl.make_record("smoke", "i" * 600, "o" * 1200, ok=1)
    assert rec["stage_label"] == frl.STAGE_LABEL["smoke"]
    assert len(rec["input"]) == 500 and len(rec["output"]) == 1000
    assert rec["ok"] is True
    assert frl.make_record("未知阶段", "", "", False)["stage_label"] == "未知阶段"


def test_group_by_run_head_rule():
    recs = [
        frl.make_record("flywheel", "", "", True),  # 组外的散记录
        frl.make_record("run", "", "", True),
        frl.make_record("flywheel", "", "", True),
        frl.make_record("register", "", "", True),
        frl.make_record("run", "", "", True),
        frl.make_record("smoke", "", "", True),
    ]
    groups = frl.group_by_run(recs)
    assert [len(g) for g in groups] == [1, 3, 2], "以 run 为组头切分"
    assert [g[0]["stage"] for g in groups] == ["flywheel", "run", "run"]


def test_build_timeline_data_shape():
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    recs = [
        frl.make_record("run", "a", "b", True),
        frl.make_record("flywheel", "a", "b", True),
        frl.make_record("smoke", "a", "b", False),
    ]
    for r in recs:
        r["date"] = today
    data = frl.build_timeline_data(recs)
    assert data["total_runs"] == 1
    assert data["total_stages"] == 3
    assert data["success_rate"] == round(2 / 3 * 100, 1)
    by_day = dict(data["by_day"])
    assert by_day[today]["total"] == 3 and by_day[today]["ok"] == 2
    assert data["recent_7d"] == 3


def test_print_list_writes_stdout(capsys):
    """列表输出用**阶段中文名**（不是 stage 英文键），并含输入/输出摘要。"""
    recs = [frl.make_record("run", "输入A", "输出B", True, {"run_id": "r9"})]
    frl.print_list(recs, limit=5)
    out = capsys.readouterr().out
    assert "共 1 条记录" in out
    assert frl.STAGE_LABEL["run"] in out
    assert "输入A" in out and "输出B" in out


def test_build_timeline_html_writes_file(tmp_path):
    """时间线 HTML 是根级活仪表盘的数据源之一：必须真的落盘且带数据锚点。"""
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    recs = [frl.make_record("run", "a", "b", True), frl.make_record("smoke", "a", "b", False)]
    for r in recs:
        r["date"] = today
    out = tmp_path / "timeline.html"
    frl.build_timeline_html(recs, out)
    html = out.read_text(encoding="utf-8")
    assert out.is_file() and len(html) > 500
    assert "flywheel" in html.lower()
