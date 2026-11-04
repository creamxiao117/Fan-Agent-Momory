# @version V1.0 / 2026-11-04 / pi / 人读每日快照的「非空壳」回归
"""**每日人读快照不得是空壳**（2026-11-04 实测修 schema 漂移）。

背景
----
`engine.py status --json` 的真实键是 **`health_scores` / `cards`**，
而 `scripts/patrol/pipeline.py::_render_daily` 原先读的是 `snap["health"]` /
`snap["platforms"]` —— 这两个键**根本不存在** ⇒ 产出的 `retro/daily-<date>.md` 里
「健康总分 / 卡片 / 平台」恒为 `—` / `{}` / `—`
⇒ **JSON 是对的、md 是空的**（连续多日入库 ⇒ 没人看 ⇒ 等于没有产物）。

⇒ 回归判据：**渲染结果必须含真实分数与卡数**，且不含空壳特征（`—（—）` / `卡片：{}`）。
⇒ 纪律：**改数据源 schema 必须同时改渲染器**（渲染器与数据源是同一条链的两端）。
"""

from scripts.patrol.pipeline import render_daily_snapshot  # noqa: E402


def _status_like() -> dict:
    """`engine.py status --json` 的**真实形状**（2026-11-04 实测键名）。"""
    return {
        "cards": {"rules": 13, "experience": 307},
        "health_scores": {"card_health": 100.0, "overall": 89.1, "gate_health": 93.8},
        "alerts": [{"level": "info", "rule": "local_llm_slow"}],
    }


def test_daily_render_is_not_empty_shell():
    md = render_daily_snapshot(_status_like(), "2026-11-04")
    assert "89.1" in md, "健康总分必须来自 health_scores.overall"
    assert "320" in md, "卡数合计必须来自 cards（13 + 307）"
    assert "—（—）" not in md
    assert "卡片：{}" not in md


def test_daily_render_shows_gate_detail_when_present():
    snap = _status_like()
    snap["gate_detail"] = {"lint": "pass", "reconcile": "warn"}
    md = render_daily_snapshot(snap, "2026-11-04")
    assert "门禁：" in md
    assert "reconcile" in md


def test_daily_render_tolerates_empty_snapshot():
    """空快照不许抛（巡检第 8 步不能因渲染失败而整链失败）。"""
    md = render_daily_snapshot({}, "2026-11-04")
    assert md.startswith("# 中枢每日快照")


def test_daily_render_shows_alerts():
    md = render_daily_snapshot(_status_like(), "2026-11-04")
    assert "告警：" in md
    assert "local_llm_slow" in md
