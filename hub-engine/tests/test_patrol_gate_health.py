"""P2-2 回归测试：健康总分必须反映巡检门禁结果（不许假绿）。

对应缺陷：`engine.py status --json` 的 health_scores 只有 4 个静态维度
（card/skill/flywheel/llm），看不见巡检自己的门禁结果——于是
「audit P0 + pytest failed」并存时总分仍是 92.0（2026-10-29 实测）。

跑法（hub-engine 根目录）：
    python -m pytest tests/test_patrol_gate_health.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from scripts.patrol.core import StepResult  # noqa: E402
from scripts.patrol_runner import _apply_gate_health  # noqa: E402


def _snap(card=100.0, skill=100.0, fly=100.0, llm=60.0, overall=92.0):
    return {
        "health_scores": {
            "card_health": card,
            "skill_health": skill,
            "flywheel_activity": fly,
            "llm_health": llm,
            "overall": overall,
        }
    }


def _steps(*pairs):
    """pairs: (name, status)"""
    return [StepResult(name=n, stage="s", status=s) for n, s in pairs]


# ── 1) 有 fail 时总分必须掉下来（核心：不许假绿）──────────────────────
def test_fail_step_lowers_overall():
    """audit fail + tests fail ⇒ 总分必须明显低于静态维度算出的 92。"""
    snap = _snap()
    before = snap["health_scores"]["overall"]
    _apply_gate_health(snap, _steps(("audit", "fail"), ("tests", "fail"), ("lint", "pass")))
    after = snap["health_scores"]["overall"]
    assert after < before, f"有 2 个 fail 时总分不该还是 {before}（实测 {after}）"


def test_gate_health_reflects_fail_ratio():
    """gate_health = 关键步的通过率：1 pass + 1 fail ⇒ 50。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("audit", "pass"), ("tests", "fail")))
    assert snap["health_scores"]["gate_health"] == 50.0


def test_all_pass_keeps_high_score():
    """全绿时 gate_health=100，总分应显著高于有 fail 的情形。"""
    snap_ok = _snap()
    _apply_gate_health(snap_ok, _steps(("audit", "pass"), ("tests", "pass"), ("lint", "pass")))
    snap_bad = _snap()
    _apply_gate_health(snap_bad, _steps(("audit", "fail"), ("tests", "fail"), ("lint", "pass")))
    assert snap_ok["health_scores"]["gate_health"] == 100.0
    assert snap_ok["health_scores"]["overall"] > snap_bad["health_scores"]["overall"]


# ── 2) 口径细节 ───────────────────────────────────────────────────────
def test_snapshot_step_excluded():
    """snapshot 步自身不参与（它就是产出快照的那一步）。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("lint", "pass"), ("snapshot", "fail")))
    assert snap["health_scores"]["gate_health"] == 100.0, "snapshot 步不应计入"


def test_skip_step_not_counted():
    """skip 不计（环境缺失不是质量问题），否则会误报低分。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("lint", "pass"), ("tests", "skip")))
    assert snap["health_scores"]["gate_health"] == 100.0


def test_warn_counts_half():
    """warn 记半分：1 pass + 1 warn ⇒ 75。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("lint", "pass"), ("reconcile", "warn")))
    assert snap["health_scores"]["gate_health"] == 75.0


def test_gate_detail_records_each_step():
    """gate_detail 落每步状态，便于事后定位是哪一步红了。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("lint", "pass"), ("audit", "fail")))
    assert snap["gate_detail"] == {"lint": "pass", "audit": "fail"}


# ── 3) 早退保护（不能把快照改坏）──────────────────────────────────────
def test_no_health_scores_leaves_snapshot_untouched():
    """没有 health_scores 时不许改 snapshot（status 失败的场景）。"""
    snap = {"cards": {"experience": 1}}
    _apply_gate_health(snap, _steps(("audit", "fail")))
    assert snap == {"cards": {"experience": 1}}


def test_empty_snapshot_is_safe():
    _apply_gate_health({}, _steps(("audit", "fail")))
    _apply_gate_health(None, _steps(("audit", "fail")))


def test_no_gate_steps_leaves_scores_untouched():
    """没有可计分的步（如全 skip）时保持原分数不动。"""
    snap = _snap()
    _apply_gate_health(snap, _steps(("lint", "skip"), ("tests", "skip")))
    assert snap["health_scores"]["overall"] == 92.0
    assert "gate_health" not in snap["health_scores"]
