# @version V3.1 / 2026-09-25 / pi / 中枢每日健康巡检编排层
"""patrol_runner.py — 中枢每日健康巡检编排层（v3.1：已拆包）

**分层**（2026-09-25 审计 §11.4 第 5 项）：

| 层 | 位置 |
|:--|:--|
| 数据模型 + 执行器 | `scripts/patrol/core.py` |
| 24 个步骤实现 | `scripts/patrol/steps.py` |
| 报告渲染 | `scripts/patrol/report.py` |
| **阶段编排（本文件）** | `_stage_*` + `run_patrol` + `main` |

本文件仍是**唯一注册表**：阶段里 `_run_step("<name>", …)` 的调用即步骤清单，
`tests/test_patrol_steps.py` 静态扫描它（新增步骤不写测试即红）。
向后兼容：旧的 `patrol_runner._step_*` / `PatrolReport` / `print_report` 等名字由下方
re-export 原样保留，调用方与测试无需改动。

用法：
  python -m scripts.patrol_runner --root <hub_root> [--dry-run|--skip-flywheel|--skip-autofix]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from scripts.patrol.core import (
    _LOCAL_TZ,
    PatrolReport,
    StageResult,
    StepResult,
    _run_cmd,
    _run_step,
)
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
    _llm_pre_check,
    _save_snapshot_archive,
    _step_auto_fix_lint,
    _step_auto_process_sleep,
    _step_auto_pytest_fix,
    _step_auto_review_today,
    _step_auto_sleep_filter,
    _step_build_vectors,
    _step_freshness_check,
    _step_hub_review,
    _step_lint,
    _step_metrics_daily,
    _step_platform_healthcheck,
    _step_platform_sync_check,
    _step_platform_unregistered,
    _step_pytest,
    _step_router_sync,
    _step_ruff,
    _step_startup_budget,
    _step_status_snapshot,
    _step_vector_regression,
    _step_verify_after_fix,
)

__all__ = [
    "PatrolReport",
    "StageResult",
    "StepResult",
    "_LOCAL_TZ",
    "_check_config_integrity",
    "_check_file_integrity",
    "_generate_suggestions",
    "_llm_pre_check",
    "_print_alerts",
    "_print_autofix_results",
    "_print_health_scores",
    "_print_stages",
    "_print_suggestions",
    "_run_cmd",
    "_run_step",
    "_save_snapshot_archive",
    "_step_auto_fix_lint",
    "_step_auto_process_sleep",
    "_step_auto_pytest_fix",
    "_step_auto_review_today",
    "_step_auto_sleep_filter",
    "_step_build_vectors",
    "_step_freshness_check",
    "_step_hub_review",
    "_step_icon",
    "_step_lint",
    "_step_metrics_daily",
    "_step_platform_healthcheck",
    "_step_platform_sync_check",
    "_step_platform_unregistered",
    "_step_pytest",
    "_step_router_sync",
    "_step_ruff",
    "_step_status_snapshot",
    "_step_startup_budget",
    "_step_vector_regression",
    "_step_verify_after_fix",
    "print_report",
    "run_patrol",
]


def _skip_if_exists_report(root: Path) -> PatrolReport | None:
    """幂等保护：今日快照已存在 → 返回「跳过版」报告；否则 None（继续正常巡检）。

    从 `run_patrol` 抽出（2026-09-25 审计 P2-b/重构 A：拆分 319 行巨型函数）。
    """
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
    # 兼容旧快照字段名 ollama → llm
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
    skipped_stage = StageResult(name="幂等保护")
    skipped_stage.steps.append(
        StepResult(
            name="check_existing_snapshot",
            stage="幂等保护",
            status="skip",
            output=f"⏭️ 今日快照已存在: {existing_snap}",
        )
    )
    report.stages.append(skipped_stage)
    return report


def _stage_infra(root: Path, report: PatrolReport) -> StageResult:
    """阶段 1：基础设施（LLM 前置检测 + 配置/目录完整性）。"""
    stage = StageResult(name="基础设施检查")
    stage.steps.append(_run_step("llm_check", "基础设施", lambda: _llm_pre_check()))
    report.llm_available = stage.steps[-1].status == "pass"
    stage.steps.append(_run_step("config_integrity", "基础设施", lambda: _check_config_integrity(root)))
    stage.steps.append(_run_step("file_integrity", "基础设施", lambda: _check_file_integrity(root)))
    return stage


def _print_dry_run_plan() -> None:
    """dry-run 的后续阶段计划（只打印，不执行）。"""
    print("[DRY-RUN] 阶段 1 完成，后续步骤仅打印计划")
    print("  阶段 2: lint → pytest → ruff (始终执行)")
    print("  阶段 3: build-vectors → router-sync")
    print("  阶段 4: vector-regression → metrics-daily → hub-review")
    print("  阶段 5: status-snapshot → archive-snapshot")
    print("  阶段 6: auto_fix_lint → auto_pytest_env_fix → auto_sleep_filter → auto_process_sleep → auto_review_today")
    print("  阶段 7: 分级输出")


def _stage_quality(root: Path, engine_dir: Path) -> StageResult:
    """阶段 2：代码质量门禁（始终执行，不依赖 LLM）。"""
    stage = StageResult(name="代码质量门禁")
    stage.steps.append(_run_step("lint", "质量门禁", lambda: _step_lint(root)))
    stage.steps.append(_run_step("pytest", "质量门禁", lambda: _step_pytest(engine_dir)))
    stage.steps.append(_run_step("ruff", "质量门禁", lambda: _step_ruff(engine_dir)))
    stage.steps.append(_run_step("startup_budget", "质量门禁", lambda: _step_startup_budget()))
    return stage


def _stage_flywheel(root: Path, engine_dir: Path, *, llm_ok: bool, skip_flywheel: bool) -> StageResult:
    """阶段 3：飞轮活跃度（本地 LLM 不可用时不构建向量）。"""
    stage = StageResult(name="飞轮活跃度")
    if skip_flywheel:
        stage.skipped = True
        stage.steps.append(
            StepResult(
                name="flywheel",
                stage="飞轮活跃度",
                status="skip",
                output="已指定 --skip-flywheel，跳过飞轮步骤",
            )
        )
        return stage
    if llm_ok:
        stage.steps.append(
            _run_step(
                "build_vectors",
                "飞轮活跃度",
                lambda: _step_build_vectors(root, engine_dir),
            )
        )
    else:
        stage.steps.append(
            StepResult(
                name="build_vectors",
                stage="飞轮活跃度",
                status="skip",
                output="本地 LLM 不可用，跳过向量构建",
            )
        )
    stage.steps.append(_run_step("router_sync", "飞轮活跃度", lambda: _step_router_sync(root, engine_dir)))
    return stage


def _stage_data_quality(root: Path, engine_dir: Path) -> StageResult:
    """阶段 4：数据质量（向量回归 / 指标 / 今日审核）。"""
    stage = StageResult(name="数据质量")
    stage.steps.append(
        _run_step(
            "vector_regression",
            "数据质量",
            lambda: _step_vector_regression(root, engine_dir),
        )
    )
    stage.steps.append(_run_step("metrics_daily", "数据质量", lambda: _step_metrics_daily(root, engine_dir)))
    stage.steps.append(_run_step("hub_review", "数据质量", lambda: _step_hub_review(root, engine_dir)))
    return stage


def _stage_report_archive(root: Path, engine_dir: Path, *, skip_if_exists: bool, report: PatrolReport) -> StageResult:
    """阶段 5：报告生成与归档（快照生成 → 归档 → 解析 alerts 到 report）。"""
    stage = StageResult(name="报告生成与归档")
    snap_result = _run_step("status_snapshot", "报告归档", lambda: _step_status_snapshot(root, engine_dir))
    stage.steps.append(snap_result)
    stage.steps.append(
        _run_step(
            "archive_snapshot",
            "报告归档",
            lambda: _save_snapshot_archive(root, engine_dir, no_overwrite=skip_if_exists),
        )
    )

    # 解析快照：把 alerts 提到 report 顶层（退出码判定要用）
    if snap_result.status == "pass":
        _exit_code, stdout, _ = _run_cmd(
            [
                sys.executable,
                str(engine_dir / "engine.py"),
                "status",
                "--root",
                str(root),
                "--json",
            ],
            cwd=engine_dir,
            timeout=60,
        )
        try:
            report.snapshot = json.loads(stdout)
            report.alerts = report.snapshot.get("alerts", [])
        except (json.JSONDecodeError, OSError):
            pass
    return stage


def _stage_autofix(root: Path, engine_dir: Path, *, skip_autofix: bool) -> StageResult:
    """阶段 6：自动修复层（v3 新增；`--skip-autofix` 时整阶段跳过）。"""
    if skip_autofix:
        stage = StageResult(name="自动修复层 (已跳过)")
        stage.skipped = True
        return stage
    stage = StageResult(name="自动修复层")
    # 6-1: lint invalid 卡自动修复（不依赖其他步骤）
    stage.steps.append(_run_step("auto_fix_lint", "自动修复", lambda: _step_auto_fix_lint(root, engine_dir)))
    # 6-2: pytest 环境类修复（pip install 缺的包）
    stage.steps.append(_run_step("auto_pytest_env_fix", "自动修复", lambda: _step_auto_pytest_fix(root, engine_dir)))
    # 6-3: sleep 候选假信号过滤
    stage.steps.append(_run_step("auto_sleep_filter", "自动修复", lambda: _step_auto_sleep_filter(root, engine_dir)))
    # 6-4: sleep 候选补 tag / 生成草稿
    stage.steps.append(_run_step("auto_process_sleep", "自动修复", lambda: _step_auto_process_sleep(root, engine_dir)))
    # 6-5: review_today 自动分类过审
    stage.steps.append(_run_step("auto_review_today", "自动修复", lambda: _step_auto_review_today(root, engine_dir)))
    return stage


def _stage_verify_after_fix(engine_dir: Path, auto_fix_results: dict, autofix_steps: list[StepResult]) -> StageResult:
    """阶段 6b：修复验证。**只有真的修过（status=fixed）才跑**，否则整阶段跳过。

    修复后必须再跑 pytest/ruff，否则「静默通过」有风险。
    """
    stage = StageResult(name="修复验证（阶段 6b）")
    if any(s.status == "fixed" for s in autofix_steps):
        stage.steps.append(
            _run_step(
                "verify_after_fix",
                "验证",
                lambda: _step_verify_after_fix(engine_dir, auto_fix_results),
            )
        )
    else:
        stage.skipped = True
    return stage


def _stage_freshness_platform(root: Path, engine_dir: Path) -> StageResult:
    """阶段 6c：知识新鲜度 + 平台层三项（MCP 块一致性 / 5 平台健康 / 未接入平台提示）。

    平台三项原先在 `A/4` 时并入本阶段（它们是「环境是否与配置一致」的同族检查）。
    """
    stage = StageResult(name="知识新鲜度（阶段 6c）")
    stage.steps.append(_run_step("freshness_check", "新鲜度", lambda: _step_freshness_check(root, engine_dir)))
    stage.steps.append(_run_step("platform_sync", "平台一致性", lambda: _step_platform_sync_check(root, engine_dir)))
    stage.steps.append(
        _run_step(
            "platform_healthcheck",
            "平台一致性",
            lambda: _step_platform_healthcheck(root, engine_dir),
        )
    )
    stage.steps.append(
        _run_step(
            "platform_unregistered",
            "平台一致性",
            lambda: _step_platform_unregistered(root, engine_dir),
        )
    )
    return stage


def _finalize_report(report: PatrolReport) -> None:
    """收尾：从各步骤退出码与 alerts 计算总体退出码，并生成改进建议。

    退出码优先级：critical 告警(3) > 任一步骤 ≥2 > 任一步骤 1 > 0。
    """
    has_critical = any(a.get("level") == "critical" for a in report.alerts)
    max_exit = 0
    for stage in report.stages:
        for step in stage.steps:
            max_exit = max(max_exit, step.exit_code)
    if has_critical:
        report.overall_exit_code = 3
    elif max_exit >= 2:
        report.overall_exit_code = 2
    elif max_exit == 1:
        report.overall_exit_code = 1
    else:
        report.overall_exit_code = 0
    report.suggestions = _generate_suggestions(report)


def run_patrol(
    root: Path,
    *,
    skip_flywheel: bool = False,
    dry_run: bool = False,
    skip_if_exists: bool = False,
    skip_autofix: bool = False,
) -> PatrolReport:
    """执行完整的 7 阶段巡检流水线（编排层；各阶段实现见 `_stage_*`）。

    Args:
        root: 中枢根目录
        skip_flywheel: 是否跳过飞轮相关步骤
        dry_run: 是否仅打印计划不实际执行
        skip_if_exists: 幂等保护：今日快照已存在则直接跳过
        skip_autofix: 跳过阶段 6 自动修复层（调试用）

    Returns:
        PatrolReport 完整巡检报告

    2026-09-25（审计 P2-b / 重构 A）：本函数从 **319 行**拆成「编排 + 9 个 `_stage_*` 函数」，
    阶段顺序、阶段名、步骤名与语义**逐字保持不变**（24 步契约测试与巡检前后报告可对比验证）。
    """
    engine_dir = Path(__file__).resolve().parent.parent

    if skip_if_exists:
        skipped = _skip_if_exists_report(root)
        if skipped is not None:
            return skipped

    report = PatrolReport(
        hub_root=str(root),
        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
    )

    # 阶段 1: 基础设施检查
    report.stages.append(_stage_infra(root, report))

    if dry_run:
        _print_dry_run_plan()
        return report

    # 阶段 2-5
    report.stages.append(_stage_quality(root, engine_dir))
    report.stages.append(_stage_flywheel(root, engine_dir, llm_ok=report.llm_available, skip_flywheel=skip_flywheel))
    report.stages.append(_stage_data_quality(root, engine_dir))
    report.stages.append(_stage_report_archive(root, engine_dir, skip_if_exists=skip_if_exists, report=report))

    # 阶段 6/6b/6c: 自动修复 → 修复验证 → 新鲜度与平台层
    stage6 = _stage_autofix(root, engine_dir, skip_autofix=skip_autofix)
    report.stages.append(stage6)
    report.auto_fix_results = {st.name: {"status": st.status, "output": st.output[:300]} for st in stage6.steps}
    report.stages.append(_stage_verify_after_fix(engine_dir, report.auto_fix_results, stage6.steps))
    report.stages.append(_stage_freshness_platform(root, engine_dir))

    _finalize_report(report)
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="patrol",
        description="中枢每日健康巡检编排 v3 (7 阶段流水线)",
    )
    parser.add_argument("--root", required=True, help="中枢根目录")
    parser.add_argument(
        "--skip-flywheel",
        action="store_true",
        help="跳过飞轮相关步骤 (向量构建/路由同步)",
    )
    parser.add_argument("--skip-autofix", action="store_true", help="跳过阶段 6 自动修复层 (调试用)")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不实际执行")
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="幂等保护：若今日快照已存在则直接跳过巡检",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出报告")
    parser.add_argument("--output", default=None, help="将报告写入指定 JSON 文件")

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not root.is_dir():
        print(f"❌ 中枢目录不存在: {root}", file=sys.stderr)
        return 1

    print(f"🔍 开始巡检 v3: {root}")
    print(f"   模式: {'dry-run' if args.dry_run else 'full'}")
    if args.skip_flywheel:
        print("   已跳过飞轮步骤")
    if args.skip_autofix:
        print("   已跳过自动修复层")
    print()

    report = run_patrol(
        root,
        skip_flywheel=args.skip_flywheel,
        dry_run=args.dry_run,
        skip_if_exists=args.skip_if_exists,
        skip_autofix=args.skip_autofix,
    )

    # 输出
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
