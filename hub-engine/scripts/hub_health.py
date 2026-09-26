"""hub-health: 采集飞轮健康度数据，供 hub-health.html 使用。

用法:
  python hub_health.py --hub-root <中枢根> --skillhub-root <SkillHub根> [--output <JSON路径>]
  python hub_health.py --hub-root <中枢根> --skillhub-root <SkillHub根> --alert [--alert-days 2]

采集指标:
  1. 飞轮转速：每天沉淀/提炼/萃取次数（基于 .sync/state/ 下的日志文件时间戳）
  2. A/E 发动机命中率：hub-index-build、hub-note-search 的调用统计
  3. B/C/D 维护站清理量：dedup、consolidate、vectorize 的记录数
  4. 技能状态分布：active/reference/deprecated 各多少
  5. 中枢卡片分布：各 type 下的卡片数量
  6. 卡片健康度：状态为 candidate/deprecated 的卡片比例
  7. 自监控告警：连续无产物 / 命中率低 → 输出建议动作
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.llm_health import LLMHealthChecker

# 飞轮各阶段对应的脚本
FLYWHEEL_STAGES = {
    "ingest": ["hub-ingest.py"],
    "build-vectors": ["build-vectors.py"],
    "dedup": ["hub-dedup.py"],
    "consolidate": ["hub-consolidate.py"],
    "lint": ["hub-lint.py"],
}


def count_files_by_pattern(directory: Path, pattern: str, days: int = 7) -> dict:
    """统计目录下匹配 pattern 的文件数量，按天分组。"""
    result = {"total": 0, "by_day": {}}
    if not directory.is_dir():
        return result
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    for f in directory.glob(pattern):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime >= cutoff:
            date_key = mtime.strftime("%Y-%m-%d")
            result["total"] += 1
            result["by_day"][date_key] = result["by_day"].get(date_key, 0) + 1
    return result


def count_scripts_run(log_dir: Path, days: int = 7) -> dict:
    """统计飞轮脚本的运行次数。"""
    stats = {}
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    for stage, scripts in FLYWHEEL_STAGES.items():
        stage_count = 0
        for script in scripts:
            script_logs = count_files_by_pattern(log_dir, f"{script}*.log", days=days)
            stage_count += script_logs["total"]
            # 也检查 query.log 中的调用
            query_log = log_dir / "query.log"
            if query_log.is_file():
                try:
                    content = query_log.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        if script in line:
                            try:
                                ts_str = line.split("|")[0].strip()
                                ts = datetime.fromisoformat(ts_str)
                                if ts >= cutoff:
                                    stage_count += 1
                            except (ValueError, IndexError):
                                pass
                except (OSError, UnicodeDecodeError):
                    pass
        stats[stage] = stage_count
    return stats


def collect_card_stats(hub_root: Path) -> dict:
    """采集中枢卡片统计。"""
    card_dirs = [
        "experience",
        "methodology",
        "rules",
        "blueprints",
        "projects",
        "longterm",
    ]
    type_counts = Counter()
    status_counts = Counter()
    card_details = []

    for d in card_dirs:
        dir_path = hub_root / d
        if not dir_path.is_dir():
            continue
        for md_file in dir_path.glob("*.md"):
            # 读取 frontmatter
            content = md_file.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            card_type = d
            card_status = "active"
            if fm_match:
                fm_text = fm_match.group(1)
                type_m = re.search(r"^type:\s*(\S+)", fm_text, re.MULTILINE)
                status_m = re.search(r"^status:\s*(\S+)", fm_text, re.MULTILINE)
                if type_m:
                    card_type = type_m.group(1)
                if status_m:
                    card_status = status_m.group(1)
            type_counts[card_type] += 1
            status_counts[card_status] += 1
            card_details.append(
                {
                    "path": str(md_file.relative_to(hub_root)),
                    "type": card_type,
                    "status": card_status,
                }
            )

    return {
        "total": len(card_details),
        "by_type": dict(type_counts),
        "by_status": dict(status_counts),
        "cards": card_details,
    }


def _resolve_skills_root(skillhub_root: Path) -> Path | None:
    """定位真正的技能目录（兼容两种布局 + 容忍调用方重复拼 /skills）。"""
    if skillhub_root is None:
        return None
    for cand in (skillhub_root, skillhub_root / "skills"):
        if not cand.is_dir():
            continue
        if next(cand.rglob("SKILL.md"), None) or next(cand.rglob("skill.yaml"), None):
            return cand
    return None


def collect_skill_stats(skillhub_root: Path) -> dict:
    """采集技能统计（同时支持 SkillHub 的 skill.yaml 与 Hermes 的 SKILL.md）。"""
    skills_root = _resolve_skills_root(skillhub_root)
    status_counts = Counter()
    skills = []

    if skills_root is None:
        return {"total": 0, "by_status": {}, "skills": [], "source": "missing"}

    # 两种布局都认：SkillHub 的 skill.yaml + Hermes 的 SKILL.md（YAML frontmatter）
    files = sorted(skills_root.rglob("skill.yaml")) + sorted(skills_root.rglob("SKILL.md"))
    import yaml

    for yaml_file in files:
        try:
            text = yaml_file.read_text(encoding="utf-8")
            try:
                if yaml_file.name == "SKILL.md":
                    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                    data = (yaml.safe_load(fm.group(1)) if fm else None) or {}
                else:
                    data = yaml.safe_load(text) or {}
            except yaml.YAMLError:
                # frontmatter 损坏也仍登记该技能（按目录名 + active），避免静默少算
                data = {}
            name = data.get("name", yaml_file.parent.name)
            # SKILL.md 无 status 字段 ⇒ 目录内已安装即视为 active
            # （旧版默认 "unknown" ⇒ active 恒 0 ⇒ 技能分恒 0，属"读不到 0"冒充"真 0"）
            status = data.get("status") or "active"
            reuse = data.get("reuse_count", 0)
            status_counts[status] += 1
            rel_path = str(yaml_file.parent.relative_to(skills_root))
            skills.append(
                {
                    "name": name,
                    "status": status,
                    "reuse_count": reuse,
                    "path": rel_path,
                }
            )
        except (OSError, ValueError, yaml.YAMLError):
            continue

    return {
        "total": len(skills),
        "by_status": dict(status_counts),
        "skills": sorted(skills, key=lambda x: x["name"]),
        "source": str(skills_root),
    }


def collect_flywheel_activity(hub_root: Path, days: int = 7) -> dict:
    """飞轮活跃度：读真实日志 .sync/state/flywheel-log.json 按「最近运行」打分。

    旧实现数 `.sync/logs/<script>*.log`，本机无该目录 ⇒ 恒 0（假告警，权重 0.2）。
    打分：100 - 8×距今天数（0 天=100，5 天=60，≥13 天=0）——与中枢既有卡实测口径一致。
    无日志/无日期 ⇒ available=False，**不冒充 0 分**。
    """
    out = {
        "available": False,
        "source": ".sync/state/flywheel-log.json",
        "runs_in_window": 0,
        "last_run_date": None,
        "days_since_last": None,
        "score": None,
    }
    log = hub_root / ".sync" / "state" / "flywheel-log.json"
    if not log.is_file():
        return out
    try:
        entries = json.loads(log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    if not isinstance(entries, list) or not entries:
        return out
    dates = sorted({e.get("date") for e in entries if isinstance(e, dict) and e.get("date")})
    if not dates:
        return out
    try:
        days_since = (datetime.now(tz=timezone.utc).date() - datetime.fromisoformat(dates[-1]).date()).days
    except ValueError:
        return out
    cutoff_day = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    out.update(
        {
            "available": True,
            "runs_in_window": sum(1 for d in dates if d >= cutoff_day),
            "last_run_date": dates[-1],
            "days_since_last": days_since,
            "score": round(max(0.0, 100.0 - 8.0 * days_since), 1),
        }
    )
    return out


def collect_llm_status() -> dict:
    """采集 Ollama 服务状态。"""
    try:
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        status = checker.get_status()
        return {
            "available": status.available,
            "url": status.url,
            "models": status.models,
            "model_count": len(status.models),
            "response_time_ms": round(status.response_time * 1000, 1),
            "last_check": datetime.fromtimestamp(status.last_check, tz=timezone.utc).isoformat()
            if status.last_check
            else None,
            "last_error": status.last_error,
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }


def compute_health_score(
    card_stats: dict,
    skill_stats: dict,
    flywheel_stats: dict,
    llm_status: dict | None = None,
    flywheel_activity: dict | None = None,
) -> dict:
    """计算飞轮健康度评分（0-100）。不可用分项记 None 并从权重中剔除。"""
    scores = {}

    # 1. 卡片健康度：active 占比（无可读卡片 ⇒ None，不冒充 0）
    # .get 兜底：调用方传入残缺统计（如 {} 或仅部分字段）时不应崩（2026-09-25 COV 实测崩过）
    total_cards = card_stats.get("total", 0)
    active_cards = (card_stats.get("by_status") or {}).get("active", 0)
    scores["card_health"] = round((active_cards / total_cards) * 100, 1) if total_cards else None

    # 2. 技能健康度：active 占比（同上）
    total_skills = skill_stats.get("total", 0)
    active_skills = (skill_stats.get("by_status") or {}).get("active", 0)
    scores["skill_health"] = round((active_skills / total_skills) * 100, 1) if total_skills else None

    # 3. 飞轮活跃度：优先用真实日志口径（collect_flywheel_activity）
    fa = flywheel_activity or {}
    if fa.get("available") and fa.get("score") is not None:
        scores["flywheel_activity"] = round(float(fa["score"]), 1)
    else:
        # 回退旧的"阶段数"口径：确实数到活动才给分，否则 None
        active_stages = sum(1 for v in flywheel_stats.values() if v > 0)
        scores["flywheel_activity"] = (
            round((active_stages / len(FLYWHEEL_STAGES)) * 100, 1) if active_stages and FLYWHEEL_STAGES else None
        )

    # 4. 本地 LLM 健康度
    # ⚠️ 2026-09-25 修正：原先默认 100.0（“未检查”当满分），与下方“读不到 ≠ 不健康”的
    # 权重归一口径**相矛盾**——会把未知一律算成满分，抬高 overall。现改为 None（从权重剔除）。
    llm_health: float | None = None
    if llm_status:
        if not llm_status.get("available", False):
            llm_health = 0.0  # 本地 LLM 不可用
        else:
            # 响应时间评分（<100ms = 100分, <500ms = 80分, 其他 = 60分）
            response_time = llm_status.get("response_time_ms", 1000)
            if response_time < 100:
                llm_health = 100.0
            elif response_time < 500:
                llm_health = 80.0
            else:
                llm_health = 60.0
    scores["llm_health"] = round(llm_health, 1) if llm_health is not None else None

    # 总分：跳过不可用分项并按可用权重归一化（"读不到" ≠ "不健康"）
    parts = [
        (scores.get("card_health"), 0.25),
        (scores.get("skill_health"), 0.35),
        (scores.get("flywheel_activity"), 0.2),
        (scores.get("llm_health"), 0.2),
    ]
    num = sum(v * w for v, w in parts if v is not None)
    den = sum(w for v, w in parts if v is not None)
    scores["overall"] = round(num / den, 1) if den else None
    scores["_weight_available"] = round(den, 2)

    return scores


def check_alerts(
    hub_root: Path,
    skillhub_root: Path,
    card_stats: dict,
    skill_stats: dict,
    flywheel_stats: dict,
    alert_days: int = 2,
) -> list[dict]:
    """自监控告警检查。

    规则:
      1. 连续 N 天无新产物 → 建议触发飞轮
      2. 命中率 < 30% → 建议触发 missing_query 补 tag
      3. active 技能中有零复用的 → 建议 run smoke-test
    """
    alerts = []

    # 规则 1: 连续无产物
    recent_log = hub_root / ".sync" / "state" / "flywheel-log.json"
    if recent_log.is_file():
        try:
            logs = json.loads(recent_log.read_text(encoding="utf-8"))
            if isinstance(logs, list) and logs:
                recent_dates = set()
                for entry in logs[-30:]:
                    d = entry.get("date", "")
                    if d:
                        recent_dates.add(d)
                from datetime import date
                from datetime import timedelta as td

                today = datetime.now(timezone.utc).date()
                days_with_logs = sorted(
                    [d for d in recent_dates if (today - date.fromisoformat(d)) <= td(days=alert_days)]
                )
                if not days_with_logs:
                    alerts.append(
                        {
                            "level": "warning",
                            "rule": "no_recent_productivity",
                            "message": f"最近 {alert_days} 天无飞轮产物，建议触发 auto_flywheel",
                            "suggestion": f"python auto_flywheel.py --root {hub_root}",
                        }
                    )
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    # 规则 2: 命中率低（读全部按日切分 + 旧版单一文件，向后兼容）
    try:
        from tools.mcp_audit import query_log_files

        log_files = query_log_files(hub_root)
    except ImportError:
        log_files = [hub_root / ".sync" / "state" / "query.log.jsonl"]

    records = []
    if log_files:
        try:
            for log_file in log_files:
                if not log_file.is_file():
                    continue
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            if records:
                searches = [r for r in records if r.get("action") == "search"]
                if searches:
                    total_searches = len(searches)
                    zero_hits = sum(1 for r in searches if int(r.get("hit_count") or 0) == 0)
                    hit_rate = 1 - (zero_hits / max(total_searches, 1))
                    if hit_rate < 0.3:
                        alerts.append(
                            {
                                "level": "warning",
                                "rule": "low_hit_rate",
                                "message": f"最近命中率 {hit_rate:.0%}，低于 30% 阈值",
                                "suggestion": f"python missing_query.py --root {hub_root} --auto-apply-p1",
                            }
                        )
        except (OSError, UnicodeDecodeError):
            pass

    # 规则 3: active 技能零复用
    zero_reuse_active = []
    for s in skill_stats.get("skills", []):
        if s.get("status") == "active" and int(s.get("reuse_count", 0) or 0) == 0:
            zero_reuse_active.append(s["name"])
    if zero_reuse_active:
        alerts.append(
            {
                "level": "info",
                "rule": "active_zero_reuse",
                "message": f"{len(zero_reuse_active)} 个 active 技能零复用，建议 run smoke-test 或标记 deprecated",
                "skills": zero_reuse_active[:10],
                "suggestion": f"python flywheel.py smoke --hub-root {hub_root} --skillhub-root {skillhub_root} --promote",
            }
        )

    # 规则 4: Ollama 不可用
    llm_status = collect_llm_status()
    if not llm_status.get("available", True):
        alerts.append(
            {
                "level": "critical",
                "rule": "ollama_unavailable",
                "message": f"本地 LLM 服务不可用 (LM Studio): {llm_status.get('last_error', '未知错误')}",
                "suggestion": "检查 LM Studio 是否在运行，确认 API 端口 1234",
            }
        )

    return alerts


def main():
    parser = argparse.ArgumentParser(description="飞轮健康度数据采集")
    parser.add_argument("--hub-root", required=True, help="记忆中枢根目录")
    parser.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    parser.add_argument("--output", help="输出 JSON 文件路径")
    parser.add_argument("--days", type=int, default=7, help="统计天数")
    parser.add_argument("--alert", action="store_true", help="运行自监控告警检查")
    parser.add_argument("--alert-days", type=int, default=2, help="告警检查的天数窗口")
    parser.add_argument(
        "--dashboard-format",
        action="store_true",
        help="输出 dashboard 专用格式（hub_health 顶层结构）",
    )
    args = parser.parse_args()

    hub_root = Path(args.hub_root).resolve()
    skillhub_root = Path(args.skillhub_root).resolve()
    log_dir = hub_root / ".sync" / "logs"

    # 采集各项数据
    card_stats = collect_card_stats(hub_root)
    skill_stats = collect_skill_stats(skillhub_root)
    flywheel_stats = count_scripts_run(log_dir, days=args.days)
    llm_status = collect_llm_status()
    flywheel_activity = collect_flywheel_activity(hub_root, days=args.days)
    health_scores = compute_health_score(card_stats, skill_stats, flywheel_stats, llm_status, flywheel_activity)

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "period_days": args.days,
        "llm_status": llm_status,
        "flywheel_stats": flywheel_stats,
        "card_stats": card_stats,
        "skill_stats": skill_stats,
        "health_scores": health_scores,
    }

    # 告警检查
    if args.alert:
        alerts = check_alerts(
            hub_root,
            skillhub_root,
            card_stats,
            skill_stats,
            flywheel_stats,
            alert_days=args.alert_days,
        )
        report["alerts"] = alerts
        if alerts:
            print("=== ⚠️ 飞轮自监控告警 ===")
            for alert in alerts:
                level_icon = {"warning": "⚠️", "info": "ℹ️", "critical": "🚨"}.get(alert["level"], "⚠️")
            # Ollama 告警使用特殊图标
            if alert.get("rule") == "ollama_unavailable":
                level_icon = "🦙"
                print(f"  {level_icon} [{alert['rule']}] {alert['message']}")
                if alert.get("suggestion"):
                    print(f"     建议: {alert['suggestion']}")
        else:
            print("=== ✅ 飞轮健康度良好，无告警 ===")

    # 输出格式
    if args.dashboard_format:
        # 构建 dashboard 专用顶层 hub_health 结构
        scores = report.get("health_scores", {})
        card_by_status = card_stats.get("by_status", {})
        skill_by_status = skill_stats.get("by_status", {})

        hub_health = {
            "overall_score": scores.get("overall"),
            "overall_verdict": (
                "✅ 健康"
                if (scores.get("overall") or 0) >= 80
                else "⚠️ 需关注"
                if (scores.get("overall") or 0) >= 60
                else "🚨 需修复"
                if scores.get("overall") is not None
                else "❓ 数据不足"
            ),
            "card_health": {
                "score": scores.get("card_health", 0),
                "active": card_by_status.get("active", 0),
                "candidate": card_by_status.get("candidate", 0),
                "reference": card_by_status.get("reference", 0),
                "archived": card_by_status.get("archived", 0),
                "total": card_stats.get("total", 0),
            },
            "skill_health": {
                "score": scores.get("skill_health", 0),
                "active": skill_by_status.get("active", 0),
                "candidate": skill_by_status.get("candidate", 0),
                "reference": skill_by_status.get("reference", 0),
                "deprecated": skill_by_status.get("deprecated", 0),
                "total": skill_stats.get("total", 0),
                "skills": [
                    {
                        "name": s["name"],
                        "status": s["status"],
                        "reuse_count": s.get("reuse_count", 0),
                    }
                    for s in skill_stats.get("skills", [])[:20]
                ],
            },
            "flywheel_activity": {
                "score": scores.get("flywheel_activity"),
                "available": flywheel_activity.get("available", False),
                "source": flywheel_activity.get("source"),
                "last_run_date": flywheel_activity.get("last_run_date"),
                "days_since_last": flywheel_activity.get("days_since_last"),
                "runs_in_window": flywheel_activity.get("runs_in_window", 0),
                "active_runs": sum(1 for v in flywheel_stats.values() if v > 0),
                "total": sum(flywheel_stats.values()),
                "by_stage": flywheel_stats,
            },
            "actions": [
                a.get("suggestion", "") or a.get("message", "")
                for a in report.get("alerts", [])
                if a.get("suggestion") or a.get("message")
            ],
        }
        output_obj = {"hub_health": hub_health, "generated_at": report["generated_at"]}
        output_text = json.dumps(output_obj, ensure_ascii=False, indent=2)
    else:
        output_text = json.dumps(report, ensure_ascii=False, indent=2)

    print(output_text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"\n已写入: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
