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
    GET  /api/snapshot          实时采集（10s 缓存）
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
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

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


# ---------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "HubDashboard/1.0"

    def log_message(self, fmt: str, *a) -> None:  # 精简日志
        if "/api/" in (a[0] if a else ""):
            sys.stderr.write(f"[api] {a[0] if a else fmt}\n")

    # ---- 响应助手
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
            return self._json(data, 200 if "error" not in data else 500)

        if path == "/api/cron/incidents":
            return self._json(cron_incidents())

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

    return Path(
        r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory"
        r"\feat-implement-plan-ZilBmv\AgentMemoryHub"
    )


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
