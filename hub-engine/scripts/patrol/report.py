# @version V3.1 / 2026-09-25 / pi / 巡检报告渲染（人类可读输出）
"""patrol.report — 巡检报告渲染层（人类可读；--json 走 `PatrolReport.to_dict`）。

拆自 `patrol_runner.py`：渲染与执行解耦后，测试可直接构造 `PatrolReport` 打样例断言。
"""

from __future__ import annotations

from scripts.patrol.core import PatrolReport

_STEP_ICONS = {"skip": "⏭️", "pass": "✅", "warn": "⚠️"}


def _step_icon(status: str) -> str:
    """步骤状态 → 图标（未知状态一律按失败显示）。"""
    return _STEP_ICONS.get(status, "❌")


def _print_stages(report: PatrolReport) -> None:
    for stage in report.stages:
        stage_icon = "⏭️" if stage.skipped else "🔧"
        print(f"\n{stage_icon} {stage.name}:")
        for step in stage.steps:
            duration = f" ({step.duration_ms:.0f}ms)" if step.duration_ms else ""
            print(f"  {_step_icon(step.status)} {step.name}{duration}: {step.output}")
            if step.error:
                print(f"     └─ 错误: {step.error}")


def _print_alerts(report: PatrolReport) -> None:
    if not report.alerts:
        print("\n✅ 无告警")
        return
    print(f"\n{'=' * 72}")
    print(f"  ⚠️ 告警汇总 ({len(report.alerts)} 项)")
    print(f"{'=' * 72}")
    level_icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
    for a in report.alerts:
        icon = level_icons.get(a.get("level", ""), "⚠️")
        print(f"  {icon} [{a.get('level', '')}] {a.get('message', '')}")
        if a.get("suggestion"):
            print(f"     💡 {a['suggestion']}")


def _print_health_scores(report: PatrolReport) -> None:
    scores = report.snapshot.get("health_scores", {})
    if not scores:
        return
    print("\n📊 健康度评分:")
    labels = {
        "card_health": "卡片",
        "skill_health": "技能",
        "flywheel_activity": "飞轮",
        "llm_health": "本地 LLM",  # v3: Ollama → 本地 LLM
        "overall": "📈 总分",
    }
    for k, v in scores.items():
        label = labels.get(k, k)
        bar_len = int(v / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {label}: {bar} {v:.1f}")


def _print_autofix_results(report: PatrolReport) -> None:
    if not report.auto_fix_results:
        return
    print("\n🔧 自动修复层结果:")
    for name, info in report.auto_fix_results.items():
        status = info["status"]
        icon = "✅" if status == "pass" else "⚠️" if status == "warn" else "⏭️"
        print(f"  {icon} {name}: {info['output'][:150]}")


def _print_suggestions(report: PatrolReport) -> None:
    if not report.suggestions:
        return
    print("\n💡 改进建议:")
    for i, s in enumerate(report.suggestions, 1):
        print(f"  {i}. {s}")


def print_report(report: PatrolReport):
    """打印巡检报告（人类可读）。

    2026-09-25（SPLIT2）：原为单函数 76 行（C901=16），拆成「表头 + 5 个 `_print_*` 段落
    渲染器 + 页脚」。段落顺序与输出文本逐字不变（tests/test_local_summary_flow.py 已断言）。
    """
    print("=" * 72)
    print("  中枢每日健康巡检报告  v3")
    print(f"  生成时间: {report.generated_at}")
    print(f"  中枢路径: {report.hub_root}")
    llm_icon = "✅ 可用" if report.llm_available else "⚠️ 不可用"
    print(f"  本地 LLM (LM Studio) 状态: {llm_icon}")
    print(f"  自动修复层: {'已执行' if report.auto_fix_results else '未执行'}")
    print("=" * 72)

    _print_stages(report)
    _print_alerts(report)
    _print_health_scores(report)
    _print_autofix_results(report)
    _print_suggestions(report)

    print(f"\n{'=' * 72}")
    print(f"  总体退出码: {report.overall_exit_code} ({'全绿' if report.overall_exit_code == 0 else '需关注'})")
    print(f"{'=' * 72}")
