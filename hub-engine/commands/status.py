# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 status + 8 helper（engine.py P1 拆分）
"""CLI 子命令：`hub status` 一键健康快照（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分 — `_cmd_status` + 8 个 helper 原样搬入。
helper 去前缀下划线（模块内私有约定）。engine.py 保留 _<name> 别名供
`monkeypatch.setattr("engine._<name>", ...)` 测试用——**测试应 patch
commands.status.collect_<name>（不被 engine 别名 shim 影响）**。
"""

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 让 commands/ 能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lint import _all_cards, lint


def cmd_status(args) -> int:
    """一键健康快照 v2：卡片分布 / Lint / LLM 健康 / 健康评分 / 告警 / 今日指标 / 最近提交"""
    import json
    from datetime import datetime, timedelta, timezone

    _LOCAL_TZ = timezone(timedelta(hours=+8))

    root = Path(args.root)

    # === 1. 静态数据收集 ===
    counts = dict(sorted(Counter(sub for sub, _p, _c in _all_cards(root)).items()))
    report = lint(root)
    pending_dir = root / ".sync" / "pending"
    pending = sorted(pending_dir.glob("*.md")) if pending_dir.is_dir() else []
    try:
        last = (
            subprocess.run(
                ["git", "log", "-1", "--format=%h %ad %s", "--date=short"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip()
            or "（无提交）"
        )
    except (subprocess.SubprocessError, OSError):
        last = "（无法读取 git 日志）"

    data = {
        "generated_at": datetime.now(_LOCAL_TZ).isoformat(),
        "root": str(root),
        "cards": counts,
        "lint": {
            "orphans": len(report["orphans"]),
            "ghosts": len(report["ghosts"]),
            "hooks": len(report["hooks"]),
            "stale": len(report["stale"]),
            "invalid": report["invalid"],
        },
        "pending": len(pending),
        "pending_first": pending[0].name if pending else None,
        "last_commit": last,
    }

    # 向量 freshness
    try:
        from tools.semsearch import scan_stale

        fresh = scan_stale(root)
        data["fresh"] = {
            "stale_total": fresh["total"],
            "stale_by_dir": fresh["stale_by_dir"],
        }
    except Exception:
        data["fresh"] = {"stale_total": -1, "stale_by_dir": {}}

    # === 2. LLM 健康检测 ===
    llm_status = collect_llm_status()
    data["llm_health"] = llm_status

    # === 3. 今日指标聚合 ===
    today_metrics = collect_today_metrics(root)
    data["today_metrics"] = today_metrics

    # === 4. 健康度评分 ===
    health_scores = compute_snapshot_health_scores(counts, report, llm_status, root)
    data["health_scores"] = health_scores

    # === 5. 自监控告警 ===
    alerts = collect_snapshot_alerts(
        report, llm_status, today_metrics, health_scores, pending
    )
    data["alerts"] = alerts

    # === 6. 与昨日快照对比 ===
    prev_snapshot = load_previous_snapshot(root)
    if prev_snapshot:
        data["comparison"] = compare_snapshots(prev_snapshot, data)

    # === 输出 ===
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_snapshot_report(data, report, pending)

    # 退出码
    has_critical = any(a["level"] == "critical" for a in alerts)
    has_warning = any(a["level"] == "warning" for a in alerts)
    lint_bad = report["invalid"] > 0 or report["orphans"] or report["ghosts"]
    if has_critical:
        return 3
    if lint_bad or has_warning:
        return 2
    return 0


def collect_llm_status() -> dict:
    """采集 LM Studio 服务状态。"""
    try:
        from tools.llm_health import LLMHealthChecker, ensure_llm_service

        # 运行时自愈（WORK.md 第20条）：离线先尝试拉起一次（手动下线标记则跳过），
        # 失败才让上层按 available=False 出 critical 告警
        ensure_llm_service()
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        checker.reset_cooldown()  # ensure 可能已在别处记录失败冷却，强制真实复查
        status = checker.get_status()
        return {
            "available": status.available,
            "url": status.url,
            "models": status.models,
            "model_count": len(status.models),
            "response_time_ms": round(status.response_time * 1000, 1),
            "last_check": (
                datetime.fromtimestamp(status.last_check, tz=timezone.utc).isoformat()
                if status.last_check
                else None
            ),
            "last_error": status.last_error,
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "url": "http://localhost:11434",
            "models": [],
            "model_count": 0,
            "response_time_ms": 0,
            "last_check": None,
            "last_error": str(e),
        }


def collect_today_metrics(root: Path) -> dict:
    """聚合今日查询指标。"""
    from tools.lint import _all_cards

    log_path = root / ".sync" / "state" / "query.log.jsonl"
    search_count = hit = miss = reuse_ops = 0

    if log_path.is_file():
        today = datetime.now(timezone(timedelta(hours=+8))).date()
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.astimezone(timezone(timedelta(hours=+8))).date() != today:
                    continue
            except ValueError:
                continue
            action = r.get("action")
            if action == "search":
                search_count += 1
                if int(r.get("hit_count") or 0) > 0:
                    hit += 1
                else:
                    miss += 1
            elif action == "reuse":
                reuse_ops += 1

    hit_rate = round(hit / search_count, 4) if search_count else None
    miss_rate = round(miss / search_count, 4) if search_count else None
    total_cards = sum(1 for _sub, _p, _c in _all_cards(root) if _c is not None)

    return {
        "date": datetime.now(timezone(timedelta(hours=+8))).date().isoformat(),
        "total_cards": total_cards,
        "searches": search_count,
        "hits": hit,
        "misses": miss,
        "hit_rate": hit_rate,
        "miss_rate": miss_rate,
        "reuse_ops": reuse_ops,
    }


def estimate_hub_tool_capacity(root: Path) -> float:
    """当 SkillHub 目录不存在时，用 hub 自身 tools/ 模块数 + MCP handlers 估算技能健康度。

    计分规则（满分 100）：
    - tools/ 可导入模块数：16 个 expected，每个 4 分（上限 64）
    - MCP handler 完整性：5 个 expected，每个 6 分（上限 30）
    - 平台适配器覆盖数：4 个 expected，每个 1.5 分（上限 6）
    """
    score = 0.0
    engine_dir = root.parent / "hub-engine"

    # tools/ 可导入模块
    engine_dir / "tools"
    expected_tools = {
        "compress",
        "dedup",
        "distill",
        "inject",
        "lint",
        "llm_health",
        "mcp_audit",
        "mcp_handlers",
        "mcp_policy",
        "memory_diff",
        "platform_bridge",
        "resilience",
        "retrieve",
        "semsearch",
        "snippet",
        "tidy",
    }
    import_ok = 0
    for mod_name in expected_tools:
        try:
            import importlib

            sys.path.insert(0, str(engine_dir))
            importlib.import_module(f"tools.{mod_name}")
            import_ok += 1
        except Exception:
            pass
    score += min(import_ok, 16) * 4  # 上限 64

    # MCP handler 完整性
    mcp_handlers = [
        "hub_search",
        "hub_get",
        "hub_index",
        "hub_bootstrap",
        "hub_ingest_candidate",
    ]
    try:
        import importlib

        sys.path.insert(0, str(engine_dir))
        mod = importlib.import_module("tools.mcp_handlers")
        present = sum(
            1 for fn in mcp_handlers if hasattr(mod, fn) and callable(getattr(mod, fn))
        )
        score += present * 6  # 上限 30
    except Exception:
        pass

    # 平台适配器覆盖
    try:
        from common.config import HubConfig

        cfg = HubConfig.load(root)
        platforms = (cfg.platforms or {}).keys()
        supported = {"hermes", "trae", "code", "workbuddy"}
        covered = sum(1 for p in platforms if p in supported)
        score += covered * 1.5  # 上限 6
    except Exception:
        pass

    return min(round(score, 1), 100.0)


def compute_snapshot_health_scores(
    counts: dict,
    report: dict,
    llm_status: dict,
    root: Path,
) -> dict:
    """计算快照健康度评分（4 维 + 总分）。"""
    total_cards = sum(counts.values())
    unhealthy_cards = len(report.get("orphans", [])) + len(report.get("ghosts", []))
    card_health = ((total_cards - unhealthy_cards) / max(total_cards, 1)) * 100

    # skill_health 默认值改为 hub 自身工具能力估算（取代硬编码 50.0）
    skill_health = estimate_hub_tool_capacity(root)
    skillhub_root = root.parent / "SkillHub"
    if skillhub_root.is_dir():
        try:
            import yaml

            skills_root = skillhub_root / "skills"
            if skills_root.is_dir():
                from collections import Counter as Ctr

                status_counts = Ctr()
                for yaml_file in skills_root.rglob("skill.yaml"):
                    try:
                        with open(yaml_file, encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                        status_counts[data.get("status", "unknown")] += 1
                    except (OSError, ValueError):
                        continue
                total_skills = sum(status_counts.values())
                active_skills = status_counts.get("active", 0)
                skill_health = (active_skills / max(total_skills, 1)) * 100
        except ImportError:
            pass

    flywheel_log = root / ".sync" / "state" / "flywheel-log.json"
    flywheel_activity = 0.0
    if flywheel_log.is_file():
        try:
            logs = json.loads(flywheel_log.read_text(encoding="utf-8"))
            if isinstance(logs, list) and logs:
                from datetime import timedelta as td

                cutoff = datetime.now(timezone.utc) - td(days=7)
                recent = 0
                for entry in logs[-30:]:
                    ts = entry.get("timestamp", "")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt >= cutoff:
                                recent += 1
                        except ValueError:
                            pass
                flywheel_activity = min(recent / 7.0, 1.0) * 100
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    llm_health = 100.0
    if not llm_status.get("available", False):
        llm_health = 0.0
    else:
        rt = llm_status.get("response_time_ms", 1000)
        if rt < 100:
            llm_health = 100.0
        elif rt < 500:
            llm_health = 80.0
        else:
            llm_health = 60.0

    overall = (
        card_health * 0.25
        + skill_health * 0.35
        + flywheel_activity * 0.20
        + llm_health * 0.20
    )

    return {
        "card_health": round(card_health, 1),
        "skill_health": round(skill_health, 1),
        "flywheel_activity": round(flywheel_activity, 1),
        "llm_health": round(llm_health, 1),
        "overall": round(overall, 1),
    }


def collect_snapshot_alerts(
    report: dict,
    llm_status: dict,
    today_metrics: dict,
    health_scores: dict,
    pending: list,
) -> list:
    """采集快照自监控告警（分级：critical / warning / info）。"""
    alerts = []

    if not llm_status.get("available", False):
        alerts.append(
            {
                "level": "critical",
                "rule": "local_llm_unavailable",
                "message": f"本地 LLM 服务不可用 (LM Studio): {llm_status.get('last_error', '未知错误')}",
                "suggestion": "检查 LM Studio 是否在运行，确认 API 端口 1234",
            }
        )

    unhealthy = (
        len(report.get("orphans", []))
        + len(report.get("ghosts", []))
        + len(report.get("stale", []))
        + report.get("invalid", 0)
    )
    if unhealthy > 0:
        alerts.append(
            {
                "level": "warning",
                "rule": "lint_issues",
                "message": f"Lint 发现 {unhealthy} 处问题：orphans={len(report.get('orphans', []))} ghosts={len(report.get('ghosts', []))} stale={len(report.get('stale', []))} invalid={report.get('invalid', 0)}",
                "suggestion": "运行 hub lint 检查详情并修复",
            }
        )

    hit_rate = today_metrics.get("hit_rate")
    if hit_rate is not None and 0 < hit_rate < 0.6:
        alerts.append(
            {
                "level": "warning",
                "rule": "low_hit_rate",
                "message": f"今日命中率 {hit_rate:.1%}，低于 60% 阈值",
                "suggestion": "检查高频未命中查询，补充卡片或优化 tags",
            }
        )

    if health_scores.get("flywheel_activity", 100) < 30:
        alerts.append(
            {
                "level": "warning",
                "rule": "low_flywheel_activity",
                "message": f"飞轮活跃度 {health_scores['flywheel_activity']}%，近 7 天活动不足",
                "suggestion": "运行 auto_flywheel.py 处理草稿，保持飞轮运转",
            }
        )

    if pending:
        alerts.append(
            {
                "level": "info",
                "rule": "pending_confirmation",
                "message": f"{len(pending)} 张卡片待人工确认",
                "suggestion": "运行 hub confirm 逐张确认 pending 目录下的卡",
            }
        )

    if llm_status.get("available") and llm_status.get("response_time_ms", 0) > 500:
        alerts.append(
            {
                "level": "info",
                "rule": "local_llm_slow",
                "message": f"本地 LLM 响应时间 (LM Studio) {llm_status['response_time_ms']}ms，建议优化",
                "suggestion": "检查 LM Studio 资源占用，考虑开启 GPU 加速或冷启动预热",
            }
        )

    return alerts


def load_previous_snapshot(root: Path) -> dict | None:
    """加载昨日快照用于对比。"""
    retro_dir = root / "retro"
    if not retro_dir.is_dir():
        return None
    yesterday = datetime.now(timezone(timedelta(hours=+8))) - timedelta(days=1)
    snapshot_path = retro_dir / f"snapshot-{yesterday.date().isoformat()}.json"
    if not snapshot_path.is_file():
        return None
    try:
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def compare_snapshots(prev: dict, curr: dict) -> dict:
    """对比两个快照的关键指标变化。"""
    changes = {}

    prev_cards = prev.get("cards", {})
    curr_cards = curr.get("cards", {})
    card_changes = {}
    for k in set(list(prev_cards.keys()) + list(curr_cards.keys())):
        delta = curr_cards.get(k, 0) - prev_cards.get(k, 0)
        if delta != 0:
            card_changes[k] = {
                "delta": delta,
                "prev": prev_cards.get(k, 0),
                "curr": curr_cards.get(k, 0),
            }
    if card_changes:
        changes["cards"] = card_changes

    prev_scores = prev.get("health_scores", {})
    curr_scores = curr.get("health_scores", {})
    score_changes = {}
    for k in set(list(prev_scores.keys()) + list(curr_scores.keys())):
        pv = prev_scores.get(k)
        cv = curr_scores.get(k)
        if pv is not None and cv is not None:
            delta = round(cv - pv, 1)
            if abs(delta) >= 1.0:
                score_changes[k] = {"delta": delta, "prev": pv, "curr": cv}
    if score_changes:
        changes["health_scores"] = score_changes

    # 变量名去 ollama 残名；`prev.get("ollama")` 键读取保留（兼容历史快照字段名）
    prev_llm = prev.get("llm_health") or prev.get("ollama", {})
    curr_llm = curr.get("llm_health") or curr.get("ollama", {})
    prev_avail = prev_llm.get("available", True)
    curr_avail = curr_llm.get("available", True)
    if prev_avail != curr_avail:
        changes["llm_status"] = {
            "prev": "available" if prev_avail else "unavailable",
            "curr": "available" if curr_avail else "unavailable",
        }

    prev_alert_rules = {a["rule"] for a in prev.get("alerts", [])}
    curr_alert_rules = {a["rule"] for a in curr.get("alerts", [])}
    new_alerts = list(curr_alert_rules - prev_alert_rules)
    resolved_alerts = list(prev_alert_rules - curr_alert_rules)
    if new_alerts or resolved_alerts:
        changes["alerts"] = {
            "new": new_alerts,
            "resolved": resolved_alerts,
        }

    return changes


def print_snapshot_report(data: dict, report: dict, pending: list):
    """打印人类可读的快照报告。"""
    print(f"生成时间: {data['generated_at']}")
    print(f"中枢: {data['root']}")
    print()

    dist = " · ".join(f"{k}={v}" for k, v in data["cards"].items()) or "（空）"
    print(f"📚 卡片分布: {dist}")
    print(
        f"🔍 Lint: 孤儿 {data['lint']['orphans']} · 幽灵 {data['lint']['ghosts']} "
        f"· hook {data['lint']['hooks']} · 陈旧 {data['lint']['stale']} · 无效 {report['invalid']}"
    )
    print(
        f"📋 待人工确认: {data['pending']}"
        + (f" → {data['pending_first']}" if data["pending_first"] else "")
    )

    fresh = data.get("fresh", {})
    fresh_total = fresh.get("stale_total", -1)
    if fresh_total >= 0:
        fresh_txt = (
            " · ".join(f"{k}={v}" for k, v in fresh.get("stale_by_dir", {}).items())
            or "无"
        )
        print(
            f"💾 向量待重建(freshness): {fresh_total} 张"
            + (f" ({fresh_txt})" if fresh_total > 0 else "")
        )
    print(f"📦 最近提交: {data['last_commit']}")

    # 变量去 ollama 残名；`data.get("ollama")` 键读取保留（兼容历史快照字段名）
    llm_health = data.get("llm_health") or data.get("ollama", {})
    if llm_health.get("available"):
        models_str = ", ".join(llm_health.get("models", [])[:3])
        print(
            f"🦙 本地 LLM 健康 (LM Studio): ✅ 可用 · {llm_health.get('model_count', 0)} 模型"
            f" · 响应 {llm_health.get('response_time_ms', 0)}ms"
            + (f" · 模型: {models_str}" if models_str else "")
        )
    else:
        print(
            f"🦙 本地 LLM 健康 (LM Studio): ❌ 不可用 · 错误: {llm_health.get('last_error', '未知')}"
        )

    scores = data.get("health_scores", {})
    if scores:
        print("\n📊 健康度评分:")
        score_labels = {
            "card_health": "卡片",
            "skill_health": "技能",
            "flywheel_activity": "飞轮",
            "llm_health": "本地 LLM",
            "overall": "📈 总分",
        }
        for k, v in scores.items():
            label = score_labels.get(k, k)
            bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
            print(f"  {label}: {bar} {v:.1f}")

    metrics = data.get("today_metrics", {})
    if metrics:
        print("\n📈 今日指标:")
        hr = metrics.get("hit_rate", "N/A")
        print(
            f"  查询 {metrics.get('searches', 0)} 次"
            f" · 命中 {metrics.get('hits', 0)}"
            f" · 命中率 {hr}"
            f" · 复用 {metrics.get('reuse_ops', 0)} 次"
        )

    alerts = data.get("alerts", [])
    if alerts:
        print(f"\n⚠️ 告警 ({len(alerts)} 项):")
        level_icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
        for a in alerts:
            icon = level_icons.get(a["level"], "⚠️")
            print(f"  {icon} [{a['level']}] {a['message']}")
            if a.get("suggestion"):
                print(f"     💡 {a['suggestion']}")
    else:
        print("\n✅ 无告警")

    comparison = data.get("comparison", {})
    if comparison:
        print("\n🔄 较昨日变化:")
        for area, changes in comparison.items():
            if area == "cards":
                for k, v in changes.items():
                    arrow = "📈" if v["delta"] > 0 else "📉" if v["delta"] < 0 else "➡️"
                    print(f"  {arrow} {k}: {v['prev']} → {v['curr']} ({v['delta']:+d})")
            elif area == "health_scores":
                for k, v in changes.items():
                    arrow = "📈" if v["delta"] > 0 else "📉"
                    print(
                        f"  {arrow} 健康分 {k}: {v['prev']} → {v['curr']} ({v['delta']:+.1f})"
                    )
            elif area == "llm_status":
                print(f"  ⚡ 本地 LLM: {changes['prev']} → {changes['curr']}")
            elif area == "alerts":
                for r in changes.get("new", []):
                    print(f"  🆕 新告警: {r}")
                for r in changes.get("resolved", []):
                    print(f"  ✅ 已消除: {r}")
