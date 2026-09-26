# @version V3.1 / 2026-09-25 / pi / 巡检包（拆分自 patrol_runner v3）
"""patrol — 每日健康巡检（编排 = `patrol_runner`，本包按层拆为 core/steps/report）。

| 模块 | 职责 |
|:--|:--|
| `patrol.core` | 数据模型（StepResult/StageResult/PatrolReport）+ `_run_step`/`_run_cmd` 执行器 |
| `patrol.steps` | 24 个步骤实现（预检/质量/飞轮/数据/自修复/平台）+ 快照归档 + 建议生成 |
| `patrol.report` | 报告渲染（人类可读） |

**注册表**：编排层的 `_run_step("<name>", …)` 是唯一事实源；`tests/test_patrol_steps.py`
会静态扫描它并要求每个名字都有对应测试（新增步骤不写测试即红）。
"""

from scripts.patrol.core import (
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
    "_step_startup_budget",
    "_step_status_snapshot",
    "_step_vector_regression",
    "_step_verify_after_fix",
    "print_report",
]
