# @version V1.0 / 2026-09-10 / Hermes / 中枢看板本地后端（静态托管+实时数据+真交互）
"""hub_dashboard_server.py - 记忆中枢看板本地后端（单文件, 仅标准库）.

为什么需要它（解决 M3 版看板的架构死结）:
    1. file:// 打开的页面 origin=null，浏览器拦截所有 127.0.0.1 请求 → Chat 必然全挂
    2. 静态 JSON 快照 → 数据永远停在生成那一刻（实测陈旧 11 小时）
    3. 无后端 → 「立即收集」「立即跑」「调用技能」只能是假按钮

路由:
    GET  /                      看板页面
    GET  /static/<path>         静态资源
    GET  /api/health            服务自检
    GET  /api/snapshot          实时采集（10s TTL + ETag/304）
    GET  /api/alert/<id>        告警详情 + 现读证据 + 可复制修复包
    POST /api/action/collect    强制重采集（绕缓存）
    POST /api/action/cron/<id>  触发定时任务  → hermes cron run <id>
    GET  /api/skill/<name>      技能详情（SKILL.md + 支撑文件清单）
    POST /api/skill/file        读技能内某个文件 {name, rel}
    POST /api/chat              <-> 本地模型对话（服务端转发，绕开 CORS）
    GET  /api/cron/incidents    定时任务故障明细

安全: 仅绑 127.0.0.1；路径穿越防护；技能文件读取限制在 skills 根内。

用法:
    python hub_dashboard_server.py --hub-root <AgentMemoryHub> [--port 8899]
    然后浏览器打开 http://127.0.0.1:8899
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

CST = timezone(timedelta(hours=8))

HERE = Path(__file__).resolve().parent
LOCAL_APP = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
SKILLS_ROOT = LOCAL_APP / "hermes" / "skills"
LM_STUDIO = "http://127.0.0.1:1234/v1"
OMNIROUTE = os.environ.get("OPENROUTER_BASE_URL") or "http://127.0.0.1:20128/v1"

STATE: dict = {
    "hub_root": None,
    "repo_root": None,
    "static_root": None,
    "snapshot": None,
    "snapshot_ts": 0.0,
    "model": None,
    "lock": threading.Lock(),
}
CACHE_TTL = 10.0  # 秒

# ---------------------------------------------------------------- P1-3 趋势历史
# 原来趋势只存在浏览器 localStorage：换设备/清缓存就归零，且无法跨端共享。
# 改为服务端把每次「有变化」的快照追加进 JSONL，前端优先读它，localStorage 只做兜底。
HIST_REL = ".sync/state/dashboard-history.jsonl"
HIST_MAX = 800  # 行数上限，超出按行截断重写（append-only 的轻量轮转）


def hist_kpis(data: dict) -> dict:
    """从快照里抽出要跟踪趋势的 KPI 序列（键名与前端 delta 一致）。"""
    hh = (data.get("hub") or {}).get("health") or {}
    vec = (data.get("hub") or {}).get("vector") or {}
    sk = data.get("skills") or {}
    cr = (data.get("runtime") or {}).get("cron") or {}
    ck = hh.get("card_health") or {}
    # 键名必须与前端 deltaBadge 用的完全一致，否则服务端历史喂不进趋势。
    return {
        "cards": ((data.get("hub") or {}).get("cards") or {}).get("total"),
        "overall": hh.get("overall_score"),
        "cron_ok": cr.get("success_rate"),
        "vector_missing": vec.get("missing"),
        # 扩展跟踪项（供后续图表复用，不参与 delta）
        "card_health": ck.get("score"),
        "skills": sk.get("total"),
        "skills_cited": sk.get("cited_any"),
        "skills_rate": sk.get("cited_rate"),
        "flywheel": ((data.get("hub") or {}).get("flywheel_real") or {}).get("score"),
        "cron_jobs": cr.get("total"),
    }


def hist_append(hub_root: Path, data: dict) -> None:
    """把本次 KPI 追加进历史（与上一行完全相同则跳过，避免刷屏）。"""
    try:
        p = Path(hub_root) / HIST_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kpi": hist_kpis(data)}
        last = None
        if p.exists():
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        last = line
            try:
                if json.loads(last or "{}").get("kpi") == row["kpi"]:
                    return
            except json.JSONDecodeError:
                pass
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # 轮转：超上限时只保留最后 HIST_MAX 行
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > HIST_MAX:
            p.write_text("\n".join(lines[-HIST_MAX:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def hist_read(hub_root: Path, limit: int = 120) -> dict:
    """读最近 limit 条历史（时间正序），供前端算 delta。"""
    p = Path(hub_root) / HIST_REL
    if not p.exists():
        return {"ok": True, "count": 0, "rows": []}
    rows = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return {"ok": False, "count": 0, "rows": []}
    return {"ok": True, "count": len(rows), "rows": rows[-limit:]}


# ---------------------------------------------------------------- 数据


def run_collect(force: bool = False) -> dict:
    """调采集器拿快照（带 TTL 缓存）。"""
    now = time.time()
    with STATE["lock"]:
        if not force and STATE["snapshot"] and (now - STATE["snapshot_ts"]) < CACHE_TTL:
            return STATE["snapshot"]

    script = STATE["repo_root"] / "hub-engine" / "scripts" / "hub_dashboard_collect.py"
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(script),
                "--hub-root",
                str(STATE["hub_root"]),
                "--repo-root",
                str(STATE["repo_root"]),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if r.returncode != 0:
            return {"error": "collect failed", "stderr": (r.stderr or "")[-800:]}
        data = json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

    with STATE["lock"]:
        STATE["snapshot"] = data
        STATE["snapshot_ts"] = time.time()
    hist_append(STATE["hub_root"], data)  # P1-3：落服务端趋势历史
    return data


def resolve_model() -> str | None:
    """从 LM Studio 挑一个可用的对话模型（排除嵌入/OCR 模型）。"""
    if STATE["model"]:
        return STATE["model"]
    try:
        with urllib.request.urlopen(f"{LM_STUDIO}/models", timeout=5) as resp:
            models = [m.get("id", "") for m in json.loads(resp.read()).get("data", [])]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None
    skip = ("embed", "bge", "ocr", "vl", "rerank")
    cands = [m for m in models if m and not any(s in m.lower() for s in skip)]
    STATE["model"] = (cands or models or [None])[0]
    return STATE["model"]


def chat(messages: list[dict], model: str | None = None) -> dict:
    """转发对话请求到本地模型（服务端发起 → 无 CORS 限制）。"""
    mdl = model or resolve_model()
    if not mdl:
        return {
            "ok": False,
            "error": "LM Studio 无可用对话模型（请确认 1234 端口已加载模型）",
        }

    body = json.dumps(
        {"model": mdl, "messages": messages, "temperature": 0.3, "stream": False}
    ).encode()
    req = urllib.request.Request(
        f"{LM_STUDIO}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read())
        text = payload["choices"][0]["message"]["content"]
        return {"ok": True, "model": mdl, "reply": text, "backend": "LM Studio"}
    except (
        urllib.error.URLError,
        OSError,
        KeyError,
        json.JSONDecodeError,
        TimeoutError,
    ) as e:
        return {
            "ok": False,
            "error": f"LM Studio 调用失败: {type(e).__name__}: {e}",
            "model": mdl,
        }


def safe_child(root: Path, rel: str) -> Path | None:
    """防路径穿越：只允许 root 内的相对路径。"""
    try:
        target = (root / rel).resolve()
        target.relative_to(root.resolve())
        return target
    except (ValueError, OSError):
        return None


def skill_detail(name: str) -> dict:
    """技能详情：SKILL.md 内容 + 支撑文件清单。"""
    if not SKILLS_ROOT.is_dir():
        return {"ok": False, "error": "技能根目录不存在"}
    # 在 skills 树下找同名技能（支持嵌套）
    hit: Path | None = None
    for sf in SKILLS_ROOT.rglob("SKILL.md"):
        if any(p.startswith(".") for p in sf.relative_to(SKILLS_ROOT).parts):
            continue
        if sf.parent.name == name:
            hit = sf.parent
            break
    if not hit:
        return {"ok": False, "error": f"未找到技能 {name}"}

    files = []
    for p in sorted(hit.rglob("*")):
        if p.is_file():
            files.append(
                {
                    "rel": str(p.relative_to(hit)).replace("\\", "/"),
                    "size": p.stat().st_size,
                }
            )
    try:
        content = (hit / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "name": name,
        "path": str(hit),
        "content": content[:20000],
        "files": files,
    }


def cron_incidents() -> dict:
    """定时任务故障明细（真实 executions.db）。"""
    import sqlite3

    db = LOCAL_APP / "hermes" / "cron" / "executions.db"
    if not db.exists():
        return {"ok": False, "error": "executions.db 不存在"}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            cols = [c[1] for c in con.execute("PRAGMA table_info(cron_incidents)")]
            rows = con.execute(
                f"SELECT {','.join(cols)} FROM cron_incidents ORDER BY rowid DESC LIMIT 30"
            ).fetchall()
        finally:
            con.close()
        return {
            "ok": True,
            "cols": cols,
            "rows": [dict(zip(cols, r, strict=False)) for r in rows],
        }
    except sqlite3.Error as e:
        return {"ok": False, "error": str(e)}


# ---- 告警详情「现读证据」辅助（按告警类别取实时状态）------------------------
# 背景：alert_detail 早期只覆盖 hub-writer-lock / git-* 两类，其余「hub 类 / cron 类」
# 告警点开只有快照里的静态 evidence，看不到「此刻真实值」，Agent 拿到修复包仍要自己再查一遍。
# 这里按告警类别补齐现读，且每类都来自与快照无关的实时数据源。


def _collector():
    """惰性导入同目录采集器模块 —— 仓库清单/命名口径的单一来源，避免两处分叉。"""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import hub_dashboard_collect

    return hub_dashboard_collect


def _live_vector() -> list[str]:
    """现读 .sync/vector.db（绕开快照 TTL，取当前真实值）。"""
    import sqlite3

    db = STATE["hub_root"] / ".sync" / "vector.db"
    if not db.exists():
        return [f"{db} 不存在（向量库尚未建立）"]
    live = [f"库文件={db}"]
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            cols = [c[1] for c in con.execute("PRAGMA table_info(docs)")]
            cards = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            embedded = (
                con.execute(
                    "SELECT COUNT(*) FROM docs WHERE embedding IS NOT NULL"
                ).fetchone()[0]
                if "embedding" in cols
                else 0
            )
        finally:
            con.close()
        live += [
            f"卡数={cards}  已嵌入={embedded}  缺失={cards - embedded}",
            f"库龄={round((time.time() - db.stat().st_mtime) / 60, 1)} 分钟",
        ]
    except (OSError, sqlite3.Error) as e:
        live.append(f"读向量库失败: {e}")
    return live


def _live_flywheel(data: dict) -> list[str]:
    """现读飞轮健康分子项，说明分数为何低。"""
    hh = (data.get("hub") or {}).get("health") or {}
    keys = (
        "overall_score",
        "overall_verdict",
        "card_health",
        "skill_health",
        "flywheel_activity",
    )
    live = [f"{k}={hh[k]}" for k in keys if k in hh]
    live += [f"行动建议: {a}" for a in (hh.get("actions") or [])]
    if hh.get("_cached"):
        live.append("(注: 该项来自采集缓存，可能滞后一个采集周期)")
    return live or ["快照未含 hub.health 分子项（该告警由旧快照推导）"]


def _live_source_health(data: dict) -> list[str]:
    """现读数据源体检逐项结果（不通过项带原始 note + 路径）。"""
    sh = data.get("source_health") or {}
    live = [f"体检项 {sh.get('total', '?')} 个，不通过 {sh.get('unhealthy', '?')} 个"]
    for c in sh.get("checks") or []:
        flag = "OK  " if c.get("ok") else "FAIL"
        live.append(f"[{flag}] {c.get('name')}（{c.get('kind')}）{c.get('note')}")
        live.append(f"        路径: {c.get('path')}")
    return live


def _live_cron(alert_id: str) -> list[str]:
    """现读 cron：任务表 jobs.json + 未处理故障 executions.db（均与快照无关）。"""
    live: list[str] = []
    jf = LOCAL_APP / "hermes" / "cron" / "jobs.json"
    try:
        if jf.exists():
            raw = json.loads(jf.read_text(encoding="utf-8"))
            jobs = raw.get("jobs", raw) if isinstance(raw, dict) else raw
            live.append(f"任务表 {jf}（实时，共 {len(jobs)} 个）")
            if alert_id == "cron-never-ran":
                for j in jobs:
                    if isinstance(j, dict) and not j.get("last_run_at"):
                        live.append(
                            f"[从未执行] {j.get('name') or j.get('id')}"
                            f"  schedule={j.get('schedule')}  enabled={j.get('enabled')}"
                            f"  next={j.get('next_run_at')}"
                        )
        else:
            live.append(f"{jf} 不存在")
    except (OSError, json.JSONDecodeError) as e:
        live.append(f"读 jobs.json 失败: {e}")

    if alert_id == "cron-incidents":
        inc = cron_incidents()
        if inc.get("ok"):
            rows = inc.get("rows") or []
            live.append(f"未处理故障 {len(rows)} 条（executions.db 实时）")
            for r in rows[:8]:
                live.append("  " + " | ".join(f"{k}={v}" for k, v in r.items()))
        else:
            live.append(f"故障明细读取失败: {inc.get('error')}")
    return live


def alert_detail(alert_id: str) -> dict:
    """告警详情 + 现读证据 + 「修复包」文本（一键复制转发给 Agent）。

    设计目标（用户明确要求）：警告里的错误信息要能点开看详情和错误日志，
    并且能复制——方便直接发给 Agent 去修。所以这里不只回详情，
    还组装一段自包含的 Markdown 修复包（症状/证据/来源/命令/关联卡），
    Agent 拿到即能动手，不必回头追问上下文。
    """
    data = run_collect()
    alerts = data.get("alerts", []) if isinstance(data, dict) else []
    hit = next((a for a in alerts if a.get("id") == alert_id), None)
    if not hit:
        return {
            "ok": False,
            "error": f"未找到告警 {alert_id}",
            "available": [a.get("id") for a in alerts],
        }

    # 现读证据：告警可能是快照采集后新增的，尽量取实时状态
    # 已覆盖类别：hub-writer-lock / git-* / hub-vector-* / flywheel-health-low /
    #            source-health / cron-* / backend-*
    live: list[str] = []
    try:
        if alert_id == "hub-writer-lock":
            lock = STATE["hub_root"] / ".sync" / "locks" / "writer.lock"
            live.append(f"锁文件存在={lock.exists()}")
            if lock.exists():
                live.append(
                    f"mtime={datetime.fromtimestamp(lock.stat().st_mtime, CST).isoformat()}"
                )
        elif alert_id.startswith("git-"):
            # 用采集器的仓库清单按「显示名」反查路径（目录名 ≠ 显示名，见 repo_list）
            name = alert_id.split("-", 2)[2]
            try:
                repos = _collector().repo_list(STATE["hub_root"], STATE["repo_root"])
            except (ImportError, AttributeError):
                repos = []
            for rname, rpath in repos:
                if rname != name:
                    continue
                out = subprocess.run(
                    ["git", "status", "--short", "--branch"],
                    cwd=str(rpath),
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                live += [ln for ln in out.stdout.splitlines()[:15] if ln.strip()]
        elif alert_id.startswith("hub-vector-"):
            live += _live_vector()
        elif alert_id == "flywheel-health-low":
            live += _live_flywheel(data)
        elif alert_id == "source-health":
            live += _live_source_health(data)
        elif alert_id.startswith("cron-"):
            live += _live_cron(alert_id)
        elif alert_id.startswith("backend-"):
            port = alert_id.split("-", 1)[1]
            url = f"http://127.0.0.1:{port}/health"
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    live.append(
                        f"{url} → HTTP {r.status}（服务已恢复？请复核告警是否已陈旧）"
                    )
            except OSError as e:
                live.append(f"{url} → 仍不可达: {e}")
    except (OSError, subprocess.SubprocessError):
        pass

    evidence = list(hit.get("evidence", [])) + (
        [f"【现读】{x}" for x in live] if live else []
    )

    pkg_lines = [
        f"## 看板告警修复包 · {hit['id']}",
        "",
        f"- **级别**: {hit['level']}",
        f"- **症状**: {hit['text']}",
        f"- **采集时间**: {data.get('generated_at', '?')}",
        f"- **定位来源**: {hit.get('source') or '(未登记)'}",
        "",
        f"**根因说明**: {hit.get('detail') or '(未登记)'}",
        "",
        "**证据**:",
        *([f"- {e}" for e in evidence] or ["- (无)"]),
        "",
        "**建议命令**:",
        *([f"```bash\n{c}\n```" for c in hit.get("cmds", [])] or ["(无)"]),
        "",
        "**关联中枢卡**:",
        *([f"- AgentMemoryHub/{d}.md" for d in hit.get("docs", [])] or ["(无)"]),
        "",
        "> 请据此定位并修复；修完请回报「告警 ID + 改动文件 + 验证方式」。",
    ]
    return {
        "ok": True,
        "alert": hit,
        "evidence": evidence,
        "repair_package": "\n".join(pkg_lines),
    }


# ---------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "HubDashboard/1.0"

    def log_message(self, fmt: str, *a) -> None:  # 精简日志
        if "/api/" in (a[0] if a else ""):
            sys.stderr.write(f"[api] {a[0] if a else fmt}\n")

    # ---- 响应助手
    def _send(
        self,
        code: int,
        body: bytes,
        ctype: str,
        *,
        etag: str | None = None,
        cache: str = "no-store",
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", etag)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, If-None-Match")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(
            code,
            json.dumps(obj, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def _json_cached(self, obj, ttl: int = 5) -> None:
        """带 ETag 的 JSON 响应：命中 If-None-Match 时回 304，省掉重传。

        P0-3：快照冷采集约 4s，但浏览器每次刷新都全量重传 JSON。
        304 让"没变化"变成几乎零成本，刷新体感从"等 4 秒"变"瞬时"。
        """
        body = json.dumps(obj, ensure_ascii=False).encode()
        etag = '"' + hashlib.sha1(body).hexdigest()[:16] + '"'
        if self.headers.get("If-None-Match") == etag:
            self._send(
                304,
                b"",
                "application/json; charset=utf-8",
                etag=etag,
                cache=f"private, max-age={ttl}",
            )
            return
        self._send(
            200,
            body,
            "application/json; charset=utf-8",
            etag=etag,
            cache=f"private, max-age={ttl}",
        )

    def _err(self, msg: str, code: int = 400) -> None:
        self._json({"ok": False, "error": msg}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    # ---- 路由
    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            f = STATE["static_root"] / "index-v4.html"
            if not f.exists():
                return self._err("index-v4.html 不存在", 404)
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")

        if path == "/api/health":
            return self._json(
                {
                    "ok": True,
                    "hub_root": str(STATE["hub_root"]),
                    "model": STATE["model"],
                    "snapshot_age_s": round(time.time() - STATE["snapshot_ts"], 1)
                    if STATE["snapshot_ts"]
                    else None,
                }
            )

        if path == "/api/snapshot":
            data = run_collect()
            if "error" in data:
                return self._json(data, 500)
            return self._json_cached(data, ttl=5)

        if path == "/api/history":
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = max(1, min(800, int((q.get("limit") or ["120"])[0])))
            except (TypeError, ValueError):
                limit = 120
            return self._json(hist_read(STATE["hub_root"], limit))

        if path == "/api/cron/incidents":
            return self._json(cron_incidents())

        if path.startswith("/api/alert/"):
            return self._json(alert_detail(unquote(path[len("/api/alert/") :])))

        if path.startswith("/api/skill/"):
            return self._json(skill_detail(unquote(path[len("/api/skill/") :])))

        # 静态资源
        rel = unquote(path[len("/static/") :]) if path.startswith("/static/") else None
        if rel:
            f = safe_child(STATE["static_root"], rel)
            if not f or not f.is_file():
                return self._err("not found", 404)
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            return self._send(200, f.read_bytes(), ctype)

        return self._err("not found", 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._body()

        if path == "/api/action/collect":
            t0 = time.time()
            data = run_collect(force=True)
            return self._json(
                {
                    "ok": "error" not in data,
                    "took_ms": round((time.time() - t0) * 1000),
                    "snapshot": data,
                }
            )

        if path.startswith("/api/action/cron/"):
            jid = unquote(path[len("/api/action/cron/") :])
            if not jid.replace("-", "").isalnum():
                return self._err("非法任务 id")
            try:
                r = subprocess.run(
                    ["hermes", "cron", "run", jid],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    shell=True,
                    check=False,
                )
                return self._json(
                    {
                        "ok": r.returncode == 0,
                        "stdout": r.stdout[-500:],
                        "stderr": r.stderr[-500:],
                    }
                )
            except (OSError, subprocess.SubprocessError) as e:
                return self._err(f"触发失败: {e}", 500)

        if path == "/api/skill/file":
            name, rel = str(body.get("name") or ""), str(body.get("rel") or "")
            det = skill_detail(name)
            if not det.get("ok"):
                return self._json(det, 404)
            f = safe_child(Path(det["path"]), rel)
            if not f or not f.is_file():
                return self._err("文件不存在或越界", 404)
            return self._json(
                {
                    "ok": True,
                    "rel": rel,
                    "size": f.stat().st_size,
                    "text": f.read_text(encoding="utf-8", errors="replace")[:40000],
                }
            )

        if path == "/api/chat":
            msgs = body.get("messages")
            if not isinstance(msgs, list) or not msgs:
                return self._err("messages 必须是非空数组")
            clean = [
                {
                    "role": str(m.get("role", "user"))[:16],
                    "content": str(m.get("content", ""))[:8000],
                }
                for m in msgs[-12:]
                if isinstance(m, dict)
            ]
            return self._json(chat(clean, body.get("model")))

        return self._err("not found", 404)


def detect_hub_root() -> Path:
    """自动探测 AgentMemoryHub 根目录.

    顺序: 环境变量 AGENT_MEMORY_HUB > cwd 向上找 > 脚本位置向上找 > 已知默认路径.
    """
    env = os.environ.get("AGENT_MEMORY_HUB")
    if env and Path(env).is_dir():
        return Path(env).resolve()

    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for base in (Path.cwd(), here.parent, here.parent.parent):
        candidates.extend([base, *base.parents])
    for c in candidates:
        if (c / "INDEX.md").exists() and (c / ".sync").is_dir():
            return c

    return here.parents[2] / "AgentMemoryHub"


def main() -> int:
    ap = argparse.ArgumentParser(description="中枢看板本地后端")
    ap.add_argument(
        "--hub-root",
        default="",
        help="AgentMemoryHub 根目录（默认自动探测）",
    )
    ap.add_argument("--repo-root", help="代码仓根（默认 hub-root 父目录）")
    ap.add_argument("--static-root", help="看板静态目录（默认 <repo>/docs/dashboard）")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    hub = Path(args.hub_root).resolve() if args.hub_root else detect_hub_root()
    repo = Path(args.repo_root).resolve() if args.repo_root else hub.parent
    static = (
        Path(args.static_root).resolve()
        if args.static_root
        else repo / "docs" / "dashboard"
    )

    if not hub.is_dir():
        print(f"[err] hub-root 不存在: {hub}")
        return 1
    STATE.update(hub_root=hub, repo_root=repo, static_root=static)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"中枢看板后端已启动: http://{args.host}:{args.port}")
    print(f"  hub-root    : {hub}")
    print(f"  static-root : {static}")
    print("  Ctrl+C 退出")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
