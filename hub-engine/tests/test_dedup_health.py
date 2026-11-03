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
3. `scripts/dedup_stats.py`：汇总分布 + 退化占比（退出码 2 = 退化中）⇒ 巡检第 4 步可见
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
