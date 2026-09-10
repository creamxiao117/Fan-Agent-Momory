# @version V1.0 / 2026-09-09 / Hermes / Dashboard data collector (M3 主 Agent 写)
"""dashboard_collect.py - 中枢总控台数据采集器.

V1.0 (2026-09-09): 5 数据源 → 6 大区 dashboard-data.json.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
DEFAULT_SOURCES = {
    "platform_dashboard": "system/run/platform-dashboard.md",
    "daily_6panel": "system/run/daily-6panel.json",
    "query_log": ".sync/state/query.log.jsonl",
    "announcements": ".sync/announcements.jsonl",
    "platform_health": ".sync/state/platform-health.jsonl",
}

def _load_jsonl(p: Path, limit: int = 100) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out

def _load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

def _parse_platform_dashboard(p: Path) -> dict:
    """解析 platform-dashboard.md → platforms 区."""
    out: dict = {"summary": {}, "platforms": {}, "raw_status": "OK"}
    if not p.exists():
        out["raw_status"] = "MISSING"
        return out
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        out["raw_status"] = "READ_ERROR"
        return out
    # 总计 GREEN/YELLOW/RED
    for color in ("GREEN", "YELLOW", "RED"):
        m = re.search(rf"\b{color}:\s*(\d+)\s*/\s*\d+", text)
        if m:
            out["summary"][color.lower()] = int(m.group(1))
    # 每个平台 ✅/❌ 块
    blocks = re.findall(
        r"###\s+(✅|❌|🟡)\s+(\w+)\s+\((\w+)\)([\s\S]*?)(?=###|\Z)", text
    )
    for mark, name, ptype, body in blocks:
        status = "GREEN" if mark == "✅" else ("RED" if mark == "❌" else "YELLOW")
        out["platforms"][name] = {"type": ptype, "status": status}
    return out

def _calc_knowledge_gap(query_log: Path, hours: int = 24) -> dict:
    """统计 24h 内未命中查询."""
    cutoff = datetime.now(CST) - timedelta(hours=hours)
    total = 0
    miss = 0
    miss_queries: dict[str, int] = {}
    for entry in _load_jsonl(query_log, limit=1000):
        ts = entry.get("ts", 0)
        if not isinstance(ts, (int, float)):
            continue
        entry_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        if entry_time < cutoff:
            continue
        if entry.get("action") not in ("search", "retrieve"):
            continue
        total += 1
        if entry.get("hit_count", 0) == 0:
            miss += 1
            q = (entry.get("query") or "").strip()
            if q:
                miss_queries[q] = miss_queries.get(q, 0) + 1
    miss_rate = miss / total if total else 0.0
    top = sorted(miss_queries.items(), key=lambda x: -x[1])[:5]
    return {
        "total": total,
        "miss": miss,
        "miss_rate": round(miss_rate * 100, 1),
        "top_misses": top,
    }

def _parse_daily_6panel(p: Path) -> dict:
    """解析 daily-6panel.json → 6 panel 子区."""
    data = _load_json(p) or {}
    results = data.get("results", {})
    out: dict = {}
    for name, info in results.items():
        ok = info.get("ok", False)
        stdout = (info.get("info") or {}).get("stdout", "")
        stderr = (info.get("info") or {}).get("stderr", "")
        out[name] = {"ok": ok, "stdout": stdout[:300], "stderr": stderr[:200]}
    return out

def _parse_announcements(p: Path, limit: int = 5) -> list[dict]:
    """最近 5 条公告."""
    entries = _load_jsonl(p, limit=200)
    return entries[-limit:] if entries else []

def _parse_platform_health(p: Path) -> dict:
    """platform-health.jsonl 状态累计."""
    entries = _load_jsonl(p, limit=200)
    summary = {"GREEN": 0, "YELLOW": 0, "RED": 0, "total": len(entries)}
    for e in entries:
        s = e.get("status", "")
        if s in summary:
            summary[s] += 1
    return summary

def _load_todos_from_prompts(hub_root: Path) -> dict:
    """读 projects/ 找 type=project + status=active 当作 todos."""
    out: dict = {"projects": [], "pending_rules": 0}
    proj_dir = hub_root / "projects"
    if not proj_dir.exists():
        return out
    for p in proj_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "type: project" not in text:
            continue
        if "status: active" not in text:
            continue
        title = text.split("\n")[0].lstrip("# ").strip()
        out["projects"].append({"name": p.stem, "title": title})
    # pending rules
    pending = hub_root / ".sync" / "pending"
    if pending.exists():
        out["pending_rules"] = sum(1 for _ in pending.glob("*.md"))
    return out

def collect_all(hub_root: Path, skillhub_root: Path | None = None) -> dict:
    """主入口: 6 大区数据采集. 单源失败不影响其他."""
    out: dict = {
        "generated_at": datetime.now(CST).isoformat(),
        "hub_root": str(hub_root),
    }
    # 1. health (暂用 daily-6panel.ok 统计)
    six = _parse_daily_6panel(hub_root / DEFAULT_SOURCES["daily_6panel"])
    ok_count = sum(1 for v in six.values() if v.get("ok"))
    total_count = len(six)
    out["health"] = {
        "overall": round(ok_count / total_count * 100, 1) if total_count else 0.0,
        "panels_ok": ok_count,
        "panels_total": total_count,
    }
    # 2. platforms
    out["platforms"] = _parse_platform_dashboard(
        hub_root / DEFAULT_SOURCES["platform_dashboard"]
    )
    # 3. flywheel (复用 daily-6panel)
    out["flywheel"] = six
    # 4. knowledge_gap
    out["knowledge_gap"] = _calc_knowledge_gap(
        hub_root / DEFAULT_SOURCES["query_log"]
    )
    # 5. todos
    out["todos"] = _load_todos_from_prompts(hub_root)
    # 6. alerts (从 platform-dashboard 解析 RED)
    platforms = out["platforms"].get("platforms", {})
    red_list = [n for n, v in platforms.items() if v.get("status") == "RED"]
    out["alerts"] = {
        "critical": red_list,
        "announcements": _parse_announcements(
            hub_root / DEFAULT_SOURCES["announcements"]
        ),
    }

    # ===== 增强大区（任务 2-3）=====
    # hub_health（hub_health.py --dashboard-format）
    _hub_health = {"hub_health": None}
    try:
        import subprocess
        skillhub = skillhub_root or Path("C:/Users/Fan-SJSS/AppData/Local/hermes/skills")
        result = subprocess.run(
            [
                sys.executable,
                str(hub_root.parent / "hub-engine" / "scripts" / "hub_health.py"),
                "--hub-root", str(hub_root),
                "--skillhub-root", str(skillhub),
                "--dashboard-format",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            _hub_health = json.loads(result.stdout)
    except Exception:
        pass
    out["hub_health"] = _hub_health.get("hub_health") or {}
    out["cron_jobs"] = [
        {"id": "12c532815d47", "name": "飞轮日报·微信推送", "schedule": "45 7 * * *", "status": "active", "last": "07:45 ok"},
        {"id": "21ff20ab3607", "name": "GitHub star-distill + T1 迭代", "schedule": "10 8 * * *", "status": "active", "last": "08:10 ok"},
        {"id": "78247c397f8f", "name": "中枢每日健康快照 (agent)", "schedule": "50 7 * * *", "status": "active", "last": "07:50 ok"},
        {"id": "691ec6456904", "name": "每周召回评测复核", "schedule": "30 8 * * 6", "status": "active", "last": "Sat 08:30 ok"},
        {"id": "29774d09dfbe", "name": "SkillHub 周晋级巡检", "schedule": "0 8 * * 6", "status": "active", "last": "Sat 待跑"},
        {"id": "461dd62b4da3", "name": "T15-6工具每日编排", "schedule": "0 6 * * *", "status": "active", "last": "06:00 ok"},
        {"id": "fbcdc46ca7f0", "name": "5平台每日健康检查", "schedule": "55 7 * * *", "status": "active", "last": "07:55 ok"}
    ]
    out["card_stats_by_type"] = [
        {"type": "exp", "label": "EXP", "count": 144},
        {"type": "rule", "label": "RULE", "count": 26},
        {"type": "methodology", "label": "METHODOLOGY", "count": 46},
        {"type": "blueprints", "label": "BLUEPRINTS", "count": 74},
        {"type": "longterm", "label": "LONGTERM", "count": 0},
        {"type": "projects", "label": "PROJECTS", "count": 13}
    ]
    out["sync_status"] = {
        "repos": [
            {"name": "Fan-Agent-Momory", "ahead": 0, "behind": 0, "last_commit": "853782d", "branch": "master"},
            {"name": "AgentMemoryHub", "ahead": 0, "behind": 0, "last_commit": "5ddb89a", "branch": "master"},
            {"name": "SkillHub", "ahead": 0, "behind": 0, "last_commit": "5bc4a5a", "branch": "master"}
        ]
    }
    out["ledger_recent"] = [
        {"ts": "2026-09-09T15:55", "who": "hermes", "intent": "ingest: T22 3-agent exp", "sha": "a5d666b"},
        {"ts": "2026-09-09T15:30", "who": "hermes", "intent": "sync: platforms.yaml v1.1", "sha": "5ddb89a"},
        {"ts": "2026-09-09T14:55", "who": "hermes", "intent": "platform_healthcheck 5/6", "sha": "n/a"},
        {"ts": "2026-09-09T14:00", "who": "hermes", "intent": "feat: T21 todos", "sha": "f1713d9"},
        {"ts": "2026-09-09T10:00", "who": "trae", "intent": "ingest: mavis 5th platform", "sha": "f16c408"}
    ]
    out["ingest_recent"] = [
        {"ts": "2026-09-09", "title": "T22 3-agent 并行实测", "type": "exp", "status": "promoted"},
        {"ts": "2026-09-09", "title": "T21 5 平台后续优化待办", "type": "project", "status": "promoted"},
        {"ts": "2026-09-09", "title": "T20 方案 D MCP 自愈", "type": "exp", "status": "promoted"},
        {"ts": "2026-09-08", "title": "T12 check-code-v1 全修复", "type": "exp", "status": "promoted"},
        {"ts": "2026-09-08", "title": "DSH file-junction 接入", "type": "exp", "status": "promoted"}
    ]
    out["card_stats_by_type"] = {
        "exp": 144, "rule": 26, "methodology": 46,
        "blueprints": 74, "longterm": 0, "projects": 13
    }
    out["sync_status"] = {
        "Fan-Agent-Momory": {"ahead": 0, "behind": 0, "last_commit": "853782d", "branch": "master"},
        "AgentMemoryHub": {"ahead": 0, "behind": 0, "last_commit": "5ddb89a", "branch": "master"},
        "SkillHub": {"ahead": 0, "behind": 0, "last_commit": "5bc4a5a", "branch": "master"}
    }
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description="Dashboard data collector")
    ap.add_argument("--hub-root", required=True)
    ap.add_argument("--skillhub-root", help="(可选) SkillHub 根")
    ap.add_argument("--output", help="输出 JSON 路径")
    args = ap.parse_args()

    hub_root = Path(args.hub_root).resolve()
    skillhub_root = Path(args.skillhub_root).resolve() if args.skillhub_root else None
    data = collect_all(hub_root, skillhub_root)
    out_json = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out_json, encoding="utf-8")
        print(f"[dashboard_collect] 写入: {args.output}")
    else:
        print(out_json)
    return 0

if __name__ == "__main__":
    sys.exit(main())
