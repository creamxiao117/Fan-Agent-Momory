# @version V4.0 / 2026-10-02 / pi / 中枢每日巡检编排层（8 步，唯一注册表 = patrol/pipeline.py）
"""patrol_runner.py — 中枢每日健康巡检编排层（v4.0：25 步 → **8 步**）

## 本轮改动的理由（M0.5/Task 7）

改造前：7 阶段 / 25 步骤 / ≥7 种报告产物，且与提交门禁、夜间生产链**大面积重复**
（ruff、预算、渲染、编码、build-vectors、ingest、distill、sleep 各在别处已跑）。
结果是巡检"什么都跑一点"，产物 7 种而**没人定期看**（T1 观测：周产出率 ≤11%）。

收口后的**职责边界**（写进代码，不靠记忆）：

| 角色 | 职责 |
|---|---|
| **提交门禁**（`common/gate_scope.py` + `scripts/gate_runner.py`） | 真值拦截：3 道 scope-gated |
| **巡检（本文件 + `patrol/pipeline.py`）** | **观测 + 对账 + 1 份快照**；不生产、不改数据（除自修复 lint） |
| **夜间链**（`scripts/nightly_consolidate.cmd`） | 生产：distill → build-vectors → render → sleep → local-summary |

**唯一注册表** = `scripts/patrol/pipeline.py::STEPS`（8 项）。本文件只做编排与报告，
`tests/test_patrol_steps.py` 从该表派生契约测试（不再正则扫源码）。

用法：
  python -m scripts.patrol_runner --root <hub_root> [--dry-run|--skip-if-exists|--json|--output FILE]
"""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

# 入口约定（同仓库 62 个脚本）：先把自己所在的 hub-engine 加进 sys.path，
# 否则 `python scripts/patrol_runner.py`（路径调用而非 `-m scripts.patrol_runner`）
# 会在 `from scripts.patrol.core import ...` 处报 ModuleNotFoundError
# （2026-10-09 体检实测：.cmd 用 `-m` 正常，人工直接跑路径即炸）。
_HUB_ENGINE = Path(__file__).resolve().parents[1]
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from scripts.patrol.core import (
    _LOCAL_TZ,
    PatrolReport,
    StageResult,
    StepResult,
    _run_cmd,
    _run_step,
)
from scripts.patrol.pipeline import IMPL, STEP_ORDER, STEPS, render_daily_snapshot
from scripts.patrol.report import (
    _print_alerts,
    _print_autofix_results,
    _print_health_scores,
    _print_stages,
    _print_suggestions,
    _step_icon,
    print_report,
)
from scripts.patrol.steps import (
    _check_config_integrity,
    _check_file_integrity,
    _generate_suggestions,
    _step_auto_fix_lint,
    _step_auto_pytest_fix,
    _step_auto_review_today,  # 同上
    _step_freshness_check,  # 待裁（Task 9）：其消费者需取证后再定去留
    _step_hub_review,  # 同上：review_today 流程的产/消两侧需一并裁定
    _step_lint,
    _step_pytest,
    _step_render_check,
    _step_router_sync,
    _step_ruff,
    _step_startup_budget,
    _step_vector_regression,
    _step_verify_after_fix,
)

__all__ = [
    "PatrolReport",
    "STEP_ORDER",
    "STEPS",
    "StageResult",
    "StepResult",
    "_LOCAL_TZ",
    "_check_config_integrity",
    "_check_file_integrity",
    "_generate_suggestions",
    "_print_alerts",
    "_print_autofix_results",
    "_print_health_scores",
    "_print_stages",
    "_print_suggestions",
    "_run_cmd",
    "_run_step",
    "_step_auto_fix_lint",
    "_step_auto_pytest_fix",
    "_step_auto_review_today",
    "_step_freshness_check",
    "_step_hub_review",
    "_step_icon",
    "_step_lint",
    "_step_pytest",
    "_step_render_check",
    "_step_router_sync",
    "_step_ruff",
    "_step_startup_budget",
    "_step_vector_regression",
    "_step_verify_after_fix",
    "print_report",
    "run_patrol",
]


def _skip_if_exists_report(root: Path) -> PatrolReport | None:
    """幂等保护：今日快照已存在 → 返回「跳过版」报告；否则 None（继续正常巡检）。"""
    retro_dir = root / "retro"
    today = datetime.now(_LOCAL_TZ).date().isoformat()
    existing_snap = retro_dir / f"snapshot-{today}.json"
    if not existing_snap.is_file():
        return None
    try:
        existing_data = json.loads(existing_snap.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not (existing_data.get("generated_at", "") and today in existing_data["generated_at"]):
        return None
    llm_field = existing_data.get("llm_health") or existing_data.get("ollama", {})
    report = PatrolReport(
        hub_root=str(root),
        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
        llm_available=llm_field.get("available", True) if isinstance(llm_field, dict) else True,
        overall_exit_code=0,
        snapshot=existing_data,
        alerts=existing_data.get("alerts", []),
        suggestions=["今日快照已存在，跳过巡检（幂等保护）"],
    )
    stage = StageResult(name="幂等保护")
    stage.steps.append(
        StepResult(
            name="check_existing_snapshot",
            stage="幂等保护",
            status="skip",
            output=f"⏭️ 今日快照已存在: {existing_snap}",
        )
    )
    report.stages.append(stage)
    return report


def _exit_code(steps: list[StepResult]) -> int:
    """0 = 全绿；2 = 有 warn（需关注）；1 = 有 fail。"""
    if any(s.status == "fail" for s in steps):
        return 1
    if any(s.status == "warn" for s in steps):
        return 2
    return 0


def _apply_gate_health(snapshot: dict, steps: list[StepResult]) -> None:
    """把**本次巡检的门禁结果**计入 health_scores（原地修改 snapshot）。

    背景（2026-10-29 实测）：`engine.py status --json` 产出的 health_scores 只有
    4 个静态维度（card/skill/flywheel/llm），**完全看不见巡检自己的门禁结果**。
    于是「audit P0=1（缺 grade 28 张）+ pytest 1 failed + recall 83%」同时存在时，
    总分依然显示 92.0（healthy）——这正是 `acceptance-net-self-audit-criteria-redlines`
    说的「假绿制造机」。

    口径：
      - `gate_health` = 参与门禁的关键步骤的通过率（fail 记 0 分，warn 记半分，skip 不计）。
      - 重算 overall：把 gate_health 作为**第 5 维度**接入，权重从其余 4 维等比缩放
        （保持 0.25/0.35/0.20/0.20 的相对比例不变，总权重仍为 1.0）。
      - snapshot 步自身不参与（它就是产出快照的那一步）。

    ⚠️ 早退条件：没有 health_scores（如 status 失败）时不动 snapshot。
    """
    if not snapshot:
        return
    scores = snapshot.get("health_scores")
    if not isinstance(scores, dict):
        return

    # 只统计**真正的门禁步**；skip 不计（环境缺失不是质量问题）。
    gate_steps = [s for s in steps if s.name != "snapshot" and s.status in ("pass", "fail", "warn")]
    if not gate_steps:
        return
    credit = sum(1.0 if s.status == "pass" else (0.5 if s.status == "warn" else 0.0) for s in gate_steps)
    gate_health = round((credit / len(gate_steps)) * 100, 1)

    base = {
        "card_health": float(scores.get("card_health") or 0.0),
        "skill_health": float(scores.get("skill_health") or 0.0),
        "flywheel_activity": float(scores.get("flywheel_activity") or 0.0),
        "llm_health": float(scores.get("llm_health") or 0.0),
    }
    weights = {"card_health": 0.25, "skill_health": 0.35, "flywheel_activity": 0.20, "llm_health": 0.20}
    # 原有 4 维权重之和 = 1.0；插入 gate_health 后按比例缩放到 (1 - GATE_WEIGHT)
    gate_weight = 0.25
    scale = (1.0 - gate_weight) / sum(weights.values())
    overall = sum(base[k] * weights[k] * scale for k in base) + gate_health * gate_weight

    scores["gate_health"] = gate_health
    scores["overall"] = round(overall, 1)
    snapshot["gate_detail"] = {s.name: s.status for s in gate_steps}


def run_patrol(root: Path, *, dry_run: bool = False, skip_if_exists: bool = False, **_deprecated) -> PatrolReport:
    """执行 8 步巡检（顺序与实现见 `patrol/pipeline.py::STEPS`）。"""
    if skip_if_exists:
        skipped = _skip_if_exists_report(root)
        if skipped is not None:
            return skipped

    report = PatrolReport(
        hub_root=str(root),
        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
        snapshot={},
    )
    # engine_dir = hub-engine（**不是** hub-engine/scripts）：engine.py / scripts 包
    # 都以其为根，旧编排层用的是 `parents[1]`。
    engine_dir = Path(__file__).resolve().parents[1]

    stage = StageResult(name="巡检（8 步）")
    all_steps: list[StepResult] = []
    for name, stage_name, fn_name in STEPS:
        if dry_run:
            r = StepResult(name=name, stage=stage_name, status="skip", output="dry-run")
        else:
            r = _run_step(name, stage_name, lambda fn=IMPL[fn_name]: fn(root, engine_dir))
        stage.steps.append(r)
        all_steps.append(r)
    report.stages.append(stage)
    report.overall_exit_code = _exit_code(all_steps)

    # 快照步把 status 的 JSON 落在 retro/；此处把它的关键字段回填进报告，供 alert/score 渲染
    snap_step = next((s for s in all_steps if s.name == "snapshot"), None)
    if snap_step is not None:
        today = datetime.now(_LOCAL_TZ).date().isoformat()
        snap_path = root / "retro" / f"snapshot-{today}.json"
        if snap_path.is_file():
            try:
                report.snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report.snapshot = {}
        # 2026-10-29（P2-2）：`engine.py status --json` 的 health_scores **只看库自身的
        # 静态指标**（卡片孤儿/技能/飞轮/LLM 延迟），看不见巡检的门禁结果——
        # 于是 audit P0 + pytest failed 同时存在时，总分仍是 92（假绿）。
        # 这里用**本次巡检的步骤结果**补一个 gate_health 维度并重算 overall，
        # 同时回写快照 JSON（落盘产物必须自洽，否则明天读到的还是旧分）。
        _apply_gate_health(report.snapshot, all_steps)
        if report.snapshot:
            with contextlib.suppress(OSError):
                snap_path.write_text(json.dumps(report.snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                # 人读 md 必须与落盘 JSON **同源**：上面回填了 gate_health 并重算 overall，
                # 若不重渲 md ⇒ md 停在回填前的分数 ⇒ md 与 json 分叉（又一处「产物说一套、账本另一套」）。
                # 2026-11-04：此处补写（当日发现 md 恒为空壳 + 与 json 不同源）。
                (root / "retro" / f"daily-{today}.md").write_text(
                    render_daily_snapshot(report.snapshot, today), encoding="utf-8"
                )
    report.alerts = (report.snapshot or {}).get("alerts", []) or []
    report.suggestions = _generate_suggestions(report)
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="patrol", description="中枢每日健康巡检 v4.0（8 步流水线）")
    parser.add_argument("--root", required=True, help="中枢根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不实际执行")
    parser.add_argument("--skip-if-exists", action="store_true", help="幂等：今日快照已存在则跳过")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出报告")
    parser.add_argument("--output", default=None, help="将报告写入指定 JSON 文件")
    # 已废弃参数（保留以免计划任务/脚本调用报错）：飞轮与自动修复已移出巡检
    parser.add_argument("--skip-flywheel", action="store_true", help="（已废弃）飞轮步骤已移出巡检")
    parser.add_argument("--skip-autofix", action="store_true", help="（已废弃）自修复只在 lint 步内进行")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"❌ 中枢目录不存在: {root}", file=sys.stderr)
        return 1

    print(f"🔍 开始巡检 v4.0（{len(STEPS)} 步）: {root}")
    print(f"   步骤: {' → '.join(STEP_ORDER)}")
    print(f"   模式: {'dry-run' if args.dry_run else 'full'}\n")

    report = run_patrol(root, dry_run=args.dry_run, skip_if_exists=args.skip_if_exists)

    if args.json or args.output:
        data = report.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json_str, encoding="utf-8")
            print(f"📄 报告已写入: {out_path}")
        if args.json:
            print(json_str)
    else:
        print_report(report)

    return report.overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
