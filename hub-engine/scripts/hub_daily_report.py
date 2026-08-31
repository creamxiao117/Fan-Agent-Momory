"""飞轮日报生成脚本（微信文字版）

复用 hub_health.py 现场采集中枢快照，排版成微信友好的中文日报文本，
输出到 stdout（供 Hermes cron 定时捕获投递）。

用法：
  python hub_daily_report.py --hub-root <中枢根> --skillhub-root <SkillHub根>

依赖：同目录 hub_health.py（--output 生成 JSON 快照）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 微信平台每行长度有限，日报控制行宽
CST = timezone(timedelta(hours=8))

# 飞轮五档中文名
FLYWHEEL_STAGES_ZH = {
    "ingest": "卡片摄取",
    "build-vectors": "向量构建",
    "dedup": "去重",
    "consolidate": "归纳整理",
    "lint": "纪律检查",
}

# 卡片类型中文名（聚合部分同义键）
CARD_TYPE_ZH = {
    "exp": "经验",
    "experience": "经验",
    "methodology": "方法论",
    "rule": "规则",
    "blueprint": "蓝图",
    "project": "项目",
    "projects": "项目",
    "longterm": "长期",
    "note": "笔记",
}

# 告警等级图标
ALERT_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}


def _collect_snapshot(hub_root: Path, skillhub_root: Path) -> dict:
    """调 hub_health.py 现场生成快照 JSON。"""
    script = Path(__file__).parent / "hub_health.py"
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    ) as fh:
        out_path = fh.name
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--hub-root",
                str(hub_root),
                "--skillhub-root",
                str(skillhub_root),
                "--alert",
                "--output",
                out_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"hub_health.py 退出码 {result.returncode}: {result.stderr[-500:]}"
            )
        report = Path(out_path)
        if not report.exists() or report.stat().st_size == 0:
            raise RuntimeError("hub_health.py 未产出快照文件")
        return json.loads(report.read_text(encoding="utf-8"))
    finally:
        try:
            Path(out_path).unlink(missing_ok=True)
        except OSError:
            pass


def _local_now_iso(utc_iso: str) -> str:
    """UTC ISO -> 本地 +08:00 中文可读时间。"""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        dt = dt.astimezone(CST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return utc_iso or "未知"


def _score_bar(score: float, width: int = 8) -> str:
    """0-100 分数转 emoji 进度条（实心/空心）。"""
    filled = round(score / 100 * width) if score > 0 else 0
    return "█" * filled + "░" * (width - filled)


def _verdict(score: float) -> str:
    """按分数给一句话评价。"""
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "需关注"
    if score >= 35:
        return "偏弱"
    return "告急"


def format_report(data: dict) -> str:
    """把快照排版成微信友好的文字版日报。"""
    hs = data.get("health_scores", {})
    overall = hs.get("overall", 0.0)
    card_health = hs.get("card_health", 0.0)
    skill_health = hs.get("skill_health", 0.0)
    flywheel_activity = hs.get("flywheel_activity", 0.0)
    llm_health = hs.get("llm_health", 0.0)

    card_stats = data.get("card_stats", {})
    flywheel_stats = data.get("flywheel_stats", {})
    skill_stats = data.get("skill_stats", {})
    llm_status = data.get("llm_status", {})
    alerts = data.get("alerts", []) or []

    gen_at = _local_now_iso(data.get("generated_at", ""))
    period_days = data.get("period_days", 7)

    lines: list[str] = []
    lines.append("📊 记忆中枢飞轮日报")
    lines.append(f"生成时间 {gen_at} · 统计窗 {period_days} 天")
    lines.append("")

    # 总览
    lines.append(f"【综合评分】{overall:.0f} / 100（{_verdict(overall)}）")
    lines.append(f"  {_score_bar(overall)}")
    lines.append("")

    # 分项
    lines.append("【健康分项】")
    lines.append(
        f"  🗂 卡片健康  {card_health:.1f}  {_score_bar(card_health)}  {_verdict(card_health)}"
    )
    lines.append(
        f"  🧩 技能健康  {skill_health:.1f}  {_score_bar(skill_health)}  {_verdict(skill_health)}"
    )
    lines.append(
        f"  🔄 飞轮活跃  {flywheel_activity:.1f}  {_score_bar(flywheel_activity)}  {_verdict(flywheel_activity)}"
    )
    lines.append(
        f"  🦙 LLM 健康  {llm_health:.1f}  {_score_bar(llm_health)}  {_verdict(llm_health)}"
    )
    lines.append("")

    # 卡片统计
    lines.append("【词条统计】")
    total = card_stats.get("total", 0)
    by_status = card_stats.get("by_status", {})
    by_type = card_stats.get("by_type", {})
    lines.append(
        f"  共 {total} 张 · 生效 {by_status.get('active', 0)} · 归档 {by_status.get('archived', 0)} · 候选 {by_status.get('candidate', 0)} · 参考 {by_status.get('reference', 0)}"
    )
    # 类型聚合（去掉 zero 项，按数量降序）
    type_agg: dict[str, int] = {}
    for key, val in by_type.items():
        zh = CARD_TYPE_ZH.get(key, key)
        type_agg[zh] = type_agg.get(zh, 0) + val
    top_types = sorted(
        ((k, v) for k, v in type_agg.items() if v > 0),
        key=lambda x: -x[1],
    )
    type_str = " · ".join(f"{k} {v}" for k, v in top_types[:6])
    if type_str:
        lines.append(f"  类型：{type_str}")
    lines.append("")

    # 技能统计
    lines.append("【技能统计】")
    s_total = skill_stats.get("total", 0)
    s_status = skill_stats.get("by_status", {})
    lines.append(
        f"  共 {s_total} 个 · 生效 {s_status.get('active', 0)} · 参考 {s_status.get('reference', 0)}"
    )
    lines.append("")

    # 飞轮五档
    lines.append("【飞轮运转 · 近 7 天】")
    if not flywheel_stats or not any(flywheel_stats.values()):
        lines.append("  本轮窗口内无飞轮运行记录")
    else:
        for stage, count in flywheel_stats.items():
            zh = FLYWHEEL_STAGES_ZH.get(stage, stage)
            mark = "✅" if count > 0 else "⏸"
            lines.append(f"  {mark} {zh}：{count} 次")

    # LLM 状态
    if llm_status:
        available = llm_status.get("available", False)
        model_count = llm_status.get("model_count", 0)
        resp = llm_status.get("response_time_ms", 0)
        resp_str = f"{resp:.0f}ms" if isinstance(resp, (int, float)) else str(resp)
        state_line = (
            f"  🟢 在线 · {model_count} 个模型 · 响应 {resp_str}"
            if available
            else "  🔴 离线（LLM 服务未就绪）"
        )
        # 响应过慢提示
        if available and isinstance(resp, (int, float)) and resp > 2000:
            state_line += " · 响应偏慢"
        lines.append(f"【LLM 服务】{state_line}")
        lines.append("")

    # 告警
    if alerts:
        lines.append("【告警提醒】")
        for alert in alerts:
            icon = ALERT_ICON.get(alert.get("level", ""), "⚠️")
            rule = alert.get("rule", "")
            message = alert.get("message", "")
            sugg = alert.get("suggestion", "")
            lines.append(f"  {icon} [{rule}] {message}")
            if sugg:
                lines.append(f"     ↳ 建议：{sugg}")
        lines.append("")

    lines.append("—— 由飞轮日报自动生成 · 数据源 hub-health.json ——")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成飞轮日报文字版")
    parser.add_argument("--hub-root", required=True, help="记忆中枢根目录")
    parser.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    parser.add_argument(
        "--json-lines",  # 供调试：顺带打印快照
        action="store_true",
        help="debug: 输出原始 JSON 快照到 stderr",
    )
    args = parser.parse_args()

    hub_root = Path(args.hub_root).resolve()
    skillhub_root = Path(args.skillhub_root).resolve()

    try:
        data = _collect_snapshot(hub_root, skillhub_root)
    except Exception as exc:  # noqa: BLE001 —— 启动门禁，须给用户明确失败信号
        print(f"❌ 飞轮日报生成失败：{exc}", file=sys.stderr)
        return 1

    if args.json_lines:
        print(json.dumps(data, ensure_ascii=False, indent=2), file=sys.stderr)

    print(format_report(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
