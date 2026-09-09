# @version V1.0 / 2026-09-09 / Hermes / MCP launcher (self-heal + multi-path + file-junction fallback)
"""MCP launcher. V1.0 (2026-09-09): 方案 D. Searches mcp_server.py across 5 paths, auto-heals once/day, falls back to file-junction."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
BACKUP_DIR_NAME = "mcp_backups"

DEFAULT_SEARCH_ROOTS = [
    Path(
        r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/hub-engine"
    ),
    Path(r"C:/Users/Fan-SJSS/AppData/Local/hermes/hub-engine"),
    Path(r"D:/AIwork/20260821-Fan-SkillHub/hub-engine"),
    Path.home() / "projects" / "hub-engine",
    Path("/opt/hub-engine"),
]

MCP_SERVER_FILENAME = "mcp_server.py"


def find_mcp_server(explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        p = Path(explicit_path).resolve()
        if p.is_file():
            return p
    for root in DEFAULT_SEARCH_ROOTS:
        candidate = root / MCP_SERVER_FILENAME
        if candidate.is_file():
            return candidate
    return None


def today_cst_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def backup_mcp_config(platform: str, config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    backup_root = config_path.parent / BACKUP_DIR_NAME
    backup_root.mkdir(exist_ok=True)
    ts = datetime.now(CST).strftime("%Y%m%d-%H%M%S")
    backup = backup_root / f"{platform}-{ts}.json"
    try:
        shutil.copy2(config_path, backup)
        return backup
    except OSError:
        return None


def can_self_heal_today(platform: str, config_path: Path) -> bool:
    backup_root = config_path.parent / BACKUP_DIR_NAME
    if not backup_root.exists():
        return True
    today = today_cst_str()
    today_count = sum(
        1 for f in backup_root.glob(f"{platform}-*.json") if today in f.name
    )
    return today_count < 1


def patch_json_args(config_path: Path, old_args: list, new_args: list) -> bool:
    try:
        with open(config_path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    mcp_servers = d.get("mcpServers", d.get("mcp_servers", {}))
    for name, conf in mcp_servers.items():
        if "agent_memory_hub" in name or "agent-memory-hub" in name:
            conf["args"] = new_args
            d["mcpServers"] = mcp_servers
            try:
                with open(config_path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(d, indent=2, ensure_ascii=False))
                return True
            except OSError:
                return False
    return False


def append_ledger(ledger_path: Path, entry: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def launch(explicit_path: str | None, hub_root: str, platform: str) -> int:
    server = find_mcp_server(explicit_path)
    if server is None:
        print(
            f"[launcher] mcp_server.py 未找到，显式路径={explicit_path}",
            file=sys.stderr,
        )
        print("[launcher] 尝试自愈：扫描 5 个候选根目录...", file=sys.stderr)
        return 1

    # 启动 mcp_server.py 子进程
    cmd = [sys.executable, str(server), "--root", hub_root]
    print(f"[launcher] 启动: {' '.join(cmd)}", file=sys.stderr)
    ledger_path = Path(hub_root) / ".sync" / "state" / "mcp_connect_ledger.jsonl"
    try:
        rc = subprocess.call(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        append_ledger(
            ledger_path,
            {
                "ts": int(time.time()),
                "platform": platform,
                "mode": "launcher",
                "server_path": str(server),
                "rc": rc,
            },
        )
        return rc
    except FileNotFoundError as exc:
        print(f"[launcher] python 不存在: {exc}", file=sys.stderr)
        return 1


def heal(platform: str, config_path: Path, hub_root: str) -> bool:
    print(f"[launcher/heal] 尝试自愈: platform={platform}", file=sys.stderr)
    if not can_self_heal_today(platform, config_path):
        print("[launcher/heal] 今日已自愈过 1 次，拒绝再次自愈", file=sys.stderr)
        return False
    new_server = find_mcp_server()
    if new_server is None:
        print(
            "[launcher/heal] 5 个候选根目录都没找到 mcp_server.py，停止自愈",
            file=sys.stderr,
        )
        return False
    backup = backup_mcp_config(platform, config_path)
    if backup is None:
        print("[launcher/heal] 备份失败，停止自愈", file=sys.stderr)
        return False
    new_args = [str(new_server), "--root", hub_root]
    if not patch_json_args(config_path, [], new_args):
        print("[launcher/heal] 改写 mcp.json 失败", file=sys.stderr)
        return False
    print(f"[launcher/heal] 已改写 mcp.json: {new_args}", file=sys.stderr)
    print(f"[launcher/heal] 备份在: {backup}", file=sys.stderr)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="hub_mcp_launcher")
    ap.add_argument(
        "--platform", required=True, choices=["hermes", "trae", "workbuddy", "code"]
    )
    ap.add_argument("--config", required=True, help="mcp.json 路径")
    ap.add_argument("--hub-root", required=True)
    ap.add_argument("--server-path", help="显式 mcp_server.py 路径")
    ap.add_argument("--heal", action="store_true", help="启动失败时尝试自愈")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[launcher] config 不存在: {config_path}", file=sys.stderr)
        return 1

    rc = launch(args.server_path, args.hub_root, args.platform)
    if rc != 0 and args.heal and heal(args.platform, config_path, args.hub_root):
        rc = launch(args.server_path, args.hub_root, args.platform)
    return rc


if __name__ == "__main__":
    sys.exit(main())
