# @version V1.0 / 2026-09-10 / Hermes / 中枢看板真实数据采集器（替换硬编码假数据）
"""hub_dashboard_collect.py - 记忆中枢看板数据采集器（全真实数据源）.

设计原则（Grafana: dashboard-as-code）:
    每个字段都能指到磁盘上的一个真实文件/进程，禁止硬编码常量。

真实数据源:
    卡片/状态        AgentMemoryHub/{rules,methodology,experience,blueprints,longterm,projects}/*.md frontmatter
    向量库           AgentMemoryHub/.sync/vector.db (sqlite, 只读)
    单写者锁         AgentMemoryHub/.sync/locks/writer.lock
    git 状态         主仓 + AgentMemoryHub (git status / rev-list)
    定时任务         %LOCALAPPDATA%/hermes/cron/jobs.json + executions.db
    后端服务         socket 探测 1234 / 20128 / 8765
    检索日志         AgentMemoryHub/.sync/state/query.log.jsonl
    飞轮健康         hub-engine/scripts/hub_health.py --dashboard-format
    技能             %LOCALAPPDATA%/hermes/skills/*/SKILL.md + 被引用次数

用法:
    python hub_dashboard_collect.py --hub-root <AgentMemoryHub> --out <json>
    python hub_dashboard_collect.py --hub-root <AgentMemoryHub>          # 打到 stdout
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
HOME = Path.home()
LOCAL_APP = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local"))
HERMES = LOCAL_APP / "hermes"
SKILLS_ROOT = HERMES / "skills"
CRON_DIR = HERMES / "cron"

# 中枢权威区目录 → 中文标签
CARD_DIRS: list[tuple[str, str]] = [
    ("rules", "规则"),
    ("methodology", "方法论"),
    ("experience", "经验"),
    ("blueprints", "蓝图"),
    ("longterm", "长期"),
    ("projects", "项目"),
]

# 后端服务探测目标
BACKENDS: list[tuple[str, int, str]] = [
    ("LM Studio", 1234, "本地推理/嵌入"),
    ("OmniRoute", 20128, "聚合网关"),
    ("本地 RAG", 8765, "语义检索服务"),
]

CARD_COUNT_CAP = 8000  # 单目录卡数上限，防扫爆


# ---------------------------------------------------------------- 工具


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 20) -> str:
    """跑外部命令，失败返回空串（不抛异常）。"""
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _probe(host: str, port: int, timeout: float = 0.7) -> tuple[bool, float]:
    """TCP 探测端口，返回 (是否存活, 耗时ms)。"""
    t0 = time.perf_counter()
    s = socket.socket()
    s.settimeout(timeout)
    try:
        alive = s.connect_ex((host, port)) == 0
    except OSError:
        alive = False
    finally:
        s.close()
    return alive, round((time.perf_counter() - t0) * 1000, 1)


def _frontmatter(p: Path) -> dict[str, str]:
    """读卡片 YAML frontmatter 的顶层标量键值（不引 yaml 依赖）。"""
    out: dict[str, str] = {}
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            if fh.readline().lstrip("\ufeff").strip() != "---":
                return out
            for _ in range(40):
                line = fh.readline()
                if not line or line.strip() == "---":
                    break
                m = re.match(r"^([A-Za-z_][\w-]*):\s*(.+?)\s*$", line)
                if m:
                    out[m.group(1).lower()] = m.group(2).strip("'\"")
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- 各区采集


def collect_cards(hub: Path) -> dict:
    """扫描权威区卡片 → 总数 / 按类型 / 按状态 / 幽灵卡。"""
    by_type: list[dict] = []
    by_status: dict[str, int] = {}
    total = 0
    no_frontmatter = 0
    newest: tuple[float, str] = (0.0, "")

    for dirname, label in CARD_DIRS:
        d = hub / dirname
        if not d.is_dir():
            by_type.append({"key": dirname, "label": label, "count": 0})
            continue
        n = 0
        for p in sorted(d.glob("*.md"))[:CARD_COUNT_CAP]:
            n += 1
            fm = _frontmatter(p)
            if not fm:
                no_frontmatter += 1
            st = (fm.get("status") or "unknown").lower()
            by_status[st] = by_status.get(st, 0) + 1
            mtime = p.stat().st_mtime
            if mtime > newest[0]:
                newest = (mtime, str(p.relative_to(hub)))
        total += n
        by_type.append({"key": dirname, "label": label, "count": n})

    order = ["active", "candidate", "reference", "archived", "unknown"]
    status_list = [
        {"key": k, "count": by_status.get(k, 0)}
        for k in order
        if by_status.get(k, 0) or k != "unknown"
    ]
    for k, v in by_status.items():
        if k not in order:
            status_list.append({"key": k, "count": v})

    return {
        "total": total,
        "by_type": by_type,
        "by_status": status_list,
        "no_frontmatter": no_frontmatter,
        "newest": {
            "path": newest[1],
            "mtime": datetime.fromtimestamp(newest[0], CST).isoformat()
            if newest[0]
            else None,
        },
    }


def collect_vector(hub: Path) -> dict:
    """读 .sync/vector.db → 卡数 / 已嵌入 / 缺失。"""
    db = hub / ".sync" / "vector.db"
    out: dict = {
        "exists": db.exists(),
        "cards": 0,
        "embedded": 0,
        "missing": 0,
        "mtime": None,
    }
    if not db.exists():
        return out
    out["mtime"] = datetime.fromtimestamp(db.stat().st_mtime, CST).isoformat()
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            cols = [c[1] for c in con.execute("PRAGMA table_info(docs)")]
            out["cards"] = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            if "embedding" in cols:
                out["embedded"] = con.execute(
                    "SELECT COUNT(*) FROM docs WHERE embedding IS NOT NULL"
                ).fetchone()[0]
            out["missing"] = out["cards"] - out["embedded"]
        finally:
            con.close()
    except sqlite3.Error as e:
        out["error"] = str(e)
    out["stale_min"] = round((time.time() - db.stat().st_mtime) / 60, 1)
    return out


def collect_git(repos: list[tuple[str, Path]]) -> list[dict]:
    """每个仓库：分支 / 领先落后 / 未提交数 / HEAD / 最近提交时间。"""
    out: list[dict] = []
    for name, path in repos:
        if not (path / ".git").exists():
            out.append({"name": name, "ok": False, "path": str(path)})
            continue
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).strip()
        head = _run(["git", "rev-parse", "--short", "HEAD"], path).strip()
        dirty = len(
            [
                x
                for x in _run(["git", "status", "--short"], path).splitlines()
                if x.strip()
            ]
        )
        ab = _run(
            ["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"], path
        ).split()
        behind, ahead = (int(ab[0]), int(ab[1])) if len(ab) == 2 else (0, 0)
        last_ts = _run(["git", "log", "-1", "--format=%cI"], path).strip()
        subject = _run(["git", "log", "-1", "--format=%s"], path).strip()
        out.append(
            {
                "name": name,
                "ok": True,
                "path": str(path),
                "branch": branch,
                "head": head,
                "dirty": dirty,
                "ahead": ahead,
                "behind": behind,
                "last_ts": last_ts,
                "last_subject": subject[:90],
            }
        )
    return out


def collect_cron() -> dict:
    """真实 cron：jobs.json（任务定义）+ executions.db（执行历史/故障）。"""
    out: dict = {
        "exists": False,
        "total": 0,
        "enabled": 0,
        "jobs": [],
        "exec_total": 0,
        "incidents_open": 0,
        "success_rate": None,
    }
    jf = CRON_DIR / "jobs.json"
    if jf.exists():
        try:
            raw = json.loads(jf.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("jobs", raw)
            if isinstance(items, dict):
                items = list(items.values())
            jobs = []
            for j in items:
                if not isinstance(j, dict):
                    continue
                sch = j.get("schedule") or {}
                jobs.append(
                    {
                        "id": str(j.get("id") or ""),
                        "name": str(j.get("name") or "(未命名)"),
                        "expr": sch.get("display") or sch.get("expr") or "",
                        "kind": sch.get("kind") or "",
                        "enabled": bool(j.get("enabled")),
                        "last_run": (
                            str(j.get("last_run") or j.get("last_run_at") or "")
                        )[:19],
                    }
                )
            jobs.sort(key=lambda x: x["last_run"], reverse=True)
            out.update(
                exists=True,
                total=len(jobs),
                enabled=sum(1 for x in jobs if x["enabled"]),
                jobs=jobs,
            )
        except (OSError, json.JSONDecodeError, AttributeError) as e:
            out["error"] = str(e)

    edb = CRON_DIR / "executions.db"
    if edb.exists():
        try:
            con = sqlite3.connect(f"file:{edb.as_posix()}?mode=ro", uri=True)
            try:
                tot = con.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
                ok = con.execute(
                    "SELECT COUNT(*) FROM executions WHERE status IN ('success','ok','completed')"
                ).fetchone()[0]
                out["exec_total"] = tot
                out["exec_ok"] = ok
                if tot:
                    out["success_rate"] = round(ok * 100.0 / tot, 1)
                try:
                    out["incidents_open"] = con.execute(
                        "SELECT COUNT(*) FROM cron_incidents WHERE closed_at IS NULL"
                    ).fetchone()[0]
                    out["incidents_total"] = con.execute(
                        "SELECT COUNT(*) FROM cron_incidents"
                    ).fetchone()[0]
                except sqlite3.Error:
                    pass
            finally:
                con.close()
        except sqlite3.Error as e:
            out["exec_error"] = str(e)
    return out


def collect_backends() -> list[dict]:
    """探测本机后端服务端口。"""
    rows = []
    for name, port, desc in BACKENDS:
        alive, ms = _probe("127.0.0.1", port)
        rows.append(
            {"name": name, "port": port, "desc": desc, "alive": alive, "ms": ms}
        )
    return rows


def collect_query_log(hub: Path) -> dict:
    """检索日志统计（修正 ts 为 ISO 字符串导致的 0 命中 bug）。"""
    p = hub / ".sync" / "state" / "query.log.jsonl"
    out: dict = {
        "exists": p.exists(),
        "total": 0,
        "last_ts": None,
        "read_24h": 0,
        "write_24h": 0,
    }
    if not p.exists():
        return out
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    last: str | None = None
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                out["total"] += 1
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = e.get("ts")
                dt = None
                if isinstance(ts_raw, str):
                    try:
                        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    except ValueError:
                        dt = None
                elif isinstance(ts_raw, (int, float)):
                    dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                if dt:
                    # 统一成带时区，避免 naive/aware 比较报 TypeError
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if last is None or ts_raw > last:
                        last = str(ts_raw)
                    if dt >= cutoff:
                        act = str(e.get("action") or "")
                        if act in ("search", "retrieve", "query", "index"):
                            out["read_24h"] += 1
                        if act in ("writeback", "ingest", "write"):
                            out["write_24h"] += 1
    except OSError:
        pass
    out["last_ts"] = last
    if last:
        try:
            lt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            out["idle_hours"] = round(
                (datetime.now(timezone.utc) - lt).total_seconds() / 3600, 1
            )
        except ValueError:
            pass
    return out


def collect_hub_health(root: Path, hub: Path) -> dict:
    """跑 hub_health.py --dashboard-format 取飞轮健康度。"""
    script = root / "hub-engine" / "scripts" / "hub_health.py"
    if not script.exists():
        return {"ok": False, "error": "hub_health.py not found"}
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(script),
                "--hub-root",
                str(hub),
                "--skillhub-root",
                str(SKILLS_ROOT),
                "--dashboard-format",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            payload = json.loads(r.stdout)
            hh = payload.get("hub_health") or payload
            hh["ok"] = True
            return hh
        return {"ok": False, "error": (r.stderr or "")[-300:]}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}


def collect_skills(hub: Path) -> dict:
    """技能清单 + 被中枢卡引用次数（真实可算的替代"复用"指标）。"""
    if not SKILLS_ROOT.is_dir():
        return {"exists": False, "total": 0, "rows": []}

    # 一次性把中枢所有卡正文读进内存，用于统计"被引用次数"
    blob: list[str] = []
    for dirname, _ in CARD_DIRS:
        d = hub / dirname
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            try:
                blob.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    haystack = "\n".join(blob)

    rows = []
    seen: set[str] = set()
    # 支撑目录中可能自带 SKILL.md 模板，不能当技能
    EXCLUDE = {
        "reference",
        "references",
        "template",
        "templates",
        "script",
        "scripts",
        "assets",
        "examples",
    }
    for sf in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        rel = sf.parent.relative_to(SKILLS_ROOT)
        # 跳过 .hub / .curator_backups 等隐藏目录 + 支撑目录
        if any(p.startswith(".") or p in EXCLUDE for p in rel.parts):
            continue
        name = rel.parts[-1]
        if name in seen:
            continue
        seen.add(name)
        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        d = sf.parent
        desc = ""
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        if m:
            desc = m.group(1).strip().strip("'\"")[:120]
        support = sum(
            1
            for sub in ("references", "templates", "scripts", "assets")
            if (d / sub).is_dir()
        )
        files = sum(1 for x in d.rglob("*") if x.is_file())
        # 被引用：用词边界匹配。
        # 不能用 substring（"reference" 会被 "references" 命中，污染成上百次），
        # 也不能只认反引号（中枢卡正文很少加反引号，会漏成 0）。
        cited = len(
            re.findall(
                r"(?<![A-Za-z0-9_\-])" + re.escape(name) + r"(?![A-Za-z0-9_\-])",
                haystack,
            )
        )
        rows.append(
            {
                "name": name,
                "group": rel.parts[0] if len(rel.parts) > 1 else "—",
                "desc": desc,
                "size": sf.stat().st_size,
                "files": files,
                "support_dirs": support,
                "mtime": datetime.fromtimestamp(sf.stat().st_mtime, CST).isoformat()[
                    :16
                ],
                "cited": cited,
            }
        )
    rows.sort(key=lambda x: (-x["cited"], x["name"]))
    return {
        "exists": True,
        "total": len(rows),
        "groups": len({r["group"] for r in rows}),
        "cited_any": sum(1 for r in rows if r["cited"] > 0),
        "rows": rows,
    }


def collect_activity(hub: Path, root: Path) -> dict:
    """最近 ingest / ledger（真实来源：git log + 卡片 mtime）。"""
    # 最近更新的卡片 = 最接近"最近 ingest"的真实信号
    recent: list[dict] = []
    cands: list[tuple[float, Path]] = []
    for dirname, label in CARD_DIRS:
        d = hub / dirname
        if d.is_dir():
            for p in d.glob("*.md"):
                try:
                    cands.append((p.stat().st_mtime, p))
                except OSError:
                    continue
    cands.sort(reverse=True)
    for mtime, p in cands[:12]:
        fm = _frontmatter(p)
        recent.append(
            {
                "title": p.stem[:80],
                "type": fm.get("type") or p.parent.name,
                "status": fm.get("status") or "?",
                "ts": datetime.fromtimestamp(mtime, CST).isoformat()[:16],
            }
        )
    # 主仓最近提交（真实）
    log = _run(["git", "log", "-12", "--format=%cI|%h|%s"], root)
    commits = []
    for line in log.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append(
                {"ts": parts[0][:16], "sha": parts[1], "subject": parts[2][:90]}
            )
    # hub 仓库最近提交
    hlog = _run(["git", "log", "-8", "--format=%cI|%h|%s"], hub)
    hcommits = []
    for line in hlog.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            hcommits.append(
                {"ts": parts[0][:16], "sha": parts[1], "subject": parts[2][:90]}
            )
    return {"recent_cards": recent, "commits": commits, "hub_commits": hcommits}


def collect_alerts(data: dict) -> list[dict]:
    """按 Grafana『告警针对症状』原则，从真实数据推导告警。"""
    out: list[dict] = []

    lock = data["hub"].get("lock", {})
    if lock.get("writer_lock"):
        out.append(
            {
                "level": "warn",
                "text": "中枢单写者锁被持有",
                "hint": "有并发写入可能，先确认进程",
            }
        )

    vec = data["hub"].get("vector", {})
    if vec.get("missing", 0) > 0:
        out.append(
            {
                "level": "warn",
                "text": f"向量库有 {vec['missing']} 张卡缺向量",
                "hint": "跑 hub build-vectors --root <Hub>",
            }
        )
    vmax = data["hub"].get("_vector_age_min", 0)
    if vmax and vmax > 24 * 60:
        out.append(
            {
                "level": "warn",
                "text": f"向量库 {vmax / 60:.0f} 小时未重建",
                "hint": "新增卡后需 build-vectors 才能被语义检索命中",
            }
        )

    cron = data["runtime"].get("cron", {})
    if cron.get("incidents_open"):
        out.append(
            {
                "level": "error",
                "text": f"{cron['incidents_open']} 个定时任务故障未处理",
                "hint": "hermes cron incidents",
            }
        )
    never = [j["name"] for j in cron.get("jobs", []) if not j.get("last_run")]
    if never:
        out.append(
            {
                "level": "warn",
                "text": f"{len(never)} 个定时任务从未执行: {', '.join(never[:2])}",
                "hint": "hermes cron list",
            }
        )

    for b in data["runtime"].get("backends", []):
        if not b["alive"]:
            out.append(
                {
                    "level": "error",
                    "text": f"后端服务 {b['name']} (: {b['port']}) 未响应",
                    "hint": b["desc"],
                }
            )

    for g in data["runtime"].get("git", []):
        if g.get("ok") and g.get("dirty", 0) >= 3:
            out.append(
                {
                    "level": "warn",
                    "text": f"{g['name']} 有 {g['dirty']} 个未提交改动",
                    "hint": "工作区守护规则: ≥3 视为有他人现场，需 commit/stash/reset",
                }
            )
        if g.get("ok") and (g.get("ahead", 0) or g.get("behind", 0)):
            out.append(
                {
                    "level": "info",
                    "text": f"{g['name']} 与远端不同步 (ahead {g.get('ahead', 0)} / behind {g.get('behind', 0)})",
                    "hint": "git push / git pull",
                }
            )

    hh = data["hub"].get("health", {})
    score = hh.get("overall_score")
    if isinstance(score, (int, float)) and score < 60:
        out.append(
            {
                "level": "warn",
                "text": f"飞轮健康度 {score} 分（< 60）",
                "hint": "查看飞轮页的分解指标",
            }
        )
    return out


# ---------------------------------------------------------------- 主入口


def collect_all(hub: Path, root: Path) -> dict:
    t0 = time.perf_counter()
    data: dict = {"schema": 2, "hub_root": str(hub)}

    data["hub"] = {
        "cards": collect_cards(hub),
        "vector": collect_vector(hub),
        "lock": {"writer_lock": (hub / ".sync" / "locks" / "writer.lock").exists()},
    }
    data["hub"]["_vector_age_min"] = data["hub"]["vector"].get("stale_min", 0)
    data["hub"]["health"] = collect_hub_health(root, hub)

    data["runtime"] = {
        "backends": collect_backends(),
        "git": collect_git([("Fan-Agent-Momory", root), ("AgentMemoryHub", hub)]),
        "cron": collect_cron(),
    }
    data["activity"] = {
        "query_log": collect_query_log(hub),
        **collect_activity(hub, root),
    }
    data["skills"] = collect_skills(hub)
    data["alerts"] = collect_alerts(data)

    data["generated_at"] = datetime.now(CST).isoformat(timespec="seconds")
    data["collect_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="中枢看板数据采集器（全真实数据源）")
    ap.add_argument("--hub-root", required=True, help="AgentMemoryHub 根目录")
    ap.add_argument("--repo-root", help="代码仓根（默认 hub-root 的父目录）")
    ap.add_argument("--out", help="输出 JSON 路径（缺省打 stdout）")
    args = ap.parse_args()

    hub = Path(args.hub_root).resolve()
    root = Path(args.repo_root).resolve() if args.repo_root else hub.parent
    data = collect_all(hub, root)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[collect] 写入 {args.out}  ({len(text)} bytes, {data['collect_ms']}ms)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
