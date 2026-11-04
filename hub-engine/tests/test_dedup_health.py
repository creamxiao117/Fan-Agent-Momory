# @version V1.0 / 2026-11-02 / pi / 去重链「退化」可观测：degraded 标记 + 台账 + 统计
"""去重链退化的**可观测性**（治「两个月后才看见的塌陷」）。

背景（2026-10-06~10-12 真实故障）
------------------------------------
本地模型普遍**漏写 `confidence`** ⇒ `parse_decision` 判成低置信 ⇒
**51 张草稿全判 review 进冲突区** ⇒ 产出率塌到 21%/17%。
当时只修了提示词（10-10）与模型配置（10-12），**没有留下「退化发生过」的痕迹** ⇒
同样的退化若再来，仍只有月后回溯周表才看得见（且指标把 review 混进「重复」，更看不出性质）。

三件套
------
1. `tools/dedup.py`：区分 **review（模型主动判不确定）** vs **degraded（模型输出坏掉）**
2. `sync.py`：每次判决 append 一行到 `.sync/state/dedup_stats.jsonl`
3. `scripts/query_report.py --dedup`：汇总分布 + 退化占比（退出码 2 = 退化中）⇒ 巡检第 4 步可见
   （2026-11-04 口径收紧：**只有「降级且未被 confirm 闭环」才退出码 2**；已闭环的只留痕不报警）
"""

import json

from scripts.query_report import dedup_summary as summarize
from tools.dedup import parse_decision


def test_missing_confidence_is_degraded_review():
    """模型漏写 confidence ⇒ 判 review **且 degraded=True**（10 月真实故障形态）。"""
    out = parse_decision('{"action":"merge","target":"x.md","reason":"重复"}')
    assert out["action"] == "review" or out["action"] == "merge"  # 动作本身合法，问题是缺 confidence
    assert out["degraded"] is True
    assert "confidence" in out["degraded_reason"]


def test_illegal_action_is_degraded():
    """非法动作 ⇒ 降级 review 且 degraded=True。"""
    out = parse_decision('{"action":"delete-everything","target":null,"reason":"x","confidence":0.9}')
    assert out["action"] == "review"
    assert out["degraded"] is True


def test_unparsable_output_is_degraded():
    """完全无法解析 ⇒ degraded=True。"""
    out = parse_decision("抱歉，我无法完成这个任务。")
    assert out["action"] == "review"
    assert out["degraded"] is True


def test_model_initiated_review_is_not_degraded():
    """模型**主动**判 review（action=review + 合法字段）⇒ **不是**退化。"""
    out = parse_decision('{"action":"review","target":null,"reason":"主题相近","confidence":0.5}')
    assert out["action"] == "review"
    assert out["degraded"] is False
    assert out["degraded_reason"] == ""


def test_valid_decision_is_not_degraded():
    out = parse_decision('{"action":"create","target":null,"reason":"主题不同","confidence":0.95}')
    assert out["action"] == "create"
    assert out["degraded"] is False
    assert out["confidence"] == 0.95


def test_stats_summary_counts_degraded(tmp_path):
    """台账汇总：动作分布 + 退化计数 + 退化占比告警。"""
    hub = tmp_path / "AgentMemoryHub"
    d = hub / ".sync" / "state"
    d.mkdir(parents=True)
    rows = [
        {"ts": "2026-11-01T01:00:00+08:00", "action": "create", "confidence": 0.9, "degraded": False},
        {
            "ts": "2026-11-01T02:00:00+08:00",
            "action": "review",
            "confidence": 0.0,
            "degraded": True,
            "degraded_reason": "模型漏写 confidence",
        },
        {
            "ts": "2026-11-01T03:00:00+08:00",
            "action": "review",
            "confidence": 0.0,
            "degraded": True,
            "degraded_reason": "模型漏写 confidence",
        },
    ]
    (d / "dedup_stats.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    s = summarize(hub, days=3650)
    assert s["total"] == 3
    assert s["degraded"] == 2
    assert s["actions"]["review"] == 2
    assert s["degraded_alert"] is True


def test_stats_empty_is_not_alert(tmp_path):
    """无数据 ⇒ 不告警（别一上来就红）。"""
    hub = tmp_path / "AgentMemoryHub"
    s = summarize(hub)
    assert s["total"] == 0
    assert s["degraded_alert"] is False


# ── 2026-11-04：告警口径收紧为「降级**且未被 confirm 闭环**」────────────────
# 退化本身不是灾难（fail-closed ⇒ 进冲突区交人工）；**没闭环才是灾难**（卡卡在冲突区没人管）。
# 闭环判据 = **文件系统事实**：权威区有同名卡（confirm 提升）/ 冲突区已无此卡（判重丢弃、合并）。


def _write_rows(hub, rows):
    d = hub / ".sync" / "state"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dedup_stats.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )


def _degraded_row(slug: str) -> dict:
    return {
        "ts": "2026-11-04T08:01:32+08:00",
        "platform": "hermes",
        "slug": slug,
        "action": "review",
        "confidence": 0.0,
        "degraded": True,
        "degraded_reason": "输出无法解析为 JSON",
    }


def test_degraded_confirmed_into_authority_does_not_alert(tmp_path):
    """降级卡**已被 confirm 提升进权威区** ⇒ 不告警。"""
    hub = tmp_path / "AgentMemoryHub"
    _write_rows(hub, [_degraded_row("foo-blueprint")])
    (hub / "blueprints").mkdir(parents=True, exist_ok=True)
    (hub / "blueprints" / "foo-blueprint.md").write_text("---\ntype: blueprint\n---\n", encoding="utf-8")
    s = summarize(hub, days=3650)
    assert s["degraded"] == 1
    assert s["degraded_confirmed"] == 1
    assert s["degraded_open"] == 0
    assert s["degraded_alert"] is False


def test_degraded_confirmed_by_commit_ledger_when_card_renamed(tmp_path):
    """**卡被 confirm 重命名落盘**（台账 slug ≠ 落盘文件名）⇒ 仍要判已闭环。

    实测形态：台账 slug `...superagent-prototype-authorization-mandate-ticket-model-blueprint`
    ↦ 落盘 `...superagent-mandate-ticket-authorization-blueprint.md`
    ⇒ 只按「权威区同名卡」查会漏判 ⇒ 以提交台账的 confirm 留痕为主判据。
    """
    hub = tmp_path / "AgentMemoryHub"
    _write_rows(hub, [_degraded_row("gh-deepseek-superagent-prototype-authorization-mandate-ticket-model-blueprint")])
    (hub / ".sync" / "state").mkdir(parents=True, exist_ok=True)
    (hub / ".sync" / "state" / "commit_ledger.jsonl").write_text(
        json.dumps(
            {
                "ts": 1793750709,
                "intent": "sync: confirm blueprint gh-deepseek-superagent-prototype-authorization-mandate-ticket-model-blueprint.md",
                "action": "commit",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    s = summarize(hub, days=3650)
    assert s["degraded_confirmed"] == 1
    assert s["degraded_open"] == 0
    assert s["degraded_alert"] is False


def test_degraded_still_sitting_in_conflicts_alerts(tmp_path):
    """退化卡**仍卡在冲突区**（待人工终审）⇒ 告警。"""
    hub = tmp_path / "AgentMemoryHub"
    _write_rows(hub, [_degraded_row("bar-blueprint")])
    cdir = hub / ".sync" / "conflicts"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "hermes_bar-blueprint.md").write_text("---\ntype: blueprint\n---\n", encoding="utf-8")
    s = summarize(hub, days=3650)
    assert s["degraded_open"] == 1
    assert s["degraded_alert"] is True
    assert s["recent_degraded"][0]["slug"] == "bar-blueprint"


def test_degraded_resolved_when_absent_from_both(tmp_path):
    """权威区没有、冲突区也没有 ⇒ 已被判重丢弃/合并 ⇒ 已闭环（单列计数，不告警）。"""
    hub = tmp_path / "AgentMemoryHub"
    _write_rows(hub, [_degraded_row("baz-blueprint")])
    s = summarize(hub, days=3650)
    assert s["degraded_resolved"] == 1
    assert s["degraded_open"] == 0
    assert s["degraded_alert"] is False


def test_closed_degradations_are_still_listed_for_traceability(tmp_path):
    """已闭环的退化**仍要留痕**（可追溯），只是不报警。"""
    hub = tmp_path / "AgentMemoryHub"
    _write_rows(hub, [_degraded_row("qux-blueprint")])
    (hub / "blueprints").mkdir(parents=True, exist_ok=True)
    (hub / "blueprints" / "qux-blueprint.md").write_text("---\ntype: blueprint\n---\n", encoding="utf-8")
    s = summarize(hub, days=3650)
    assert s["recent_degraded"] == []
    assert s["recent_degraded_closed"][0]["slug"] == "qux-blueprint"
    assert s["recent_degraded_closed"][0]["state"] == "confirmed"
