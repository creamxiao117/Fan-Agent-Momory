# @version V1.0 / 2026-09-09 / Hermes / 5 平台统一健康检查
"""platform_healthcheck - 5 平台统一健康检查器.

V1.0 (2026-09-09):
  - 读 system/platforms.yaml (schema 1.1)
  - 对 mcp 平台检查 launcher/args/python
  - 对 file 平台检查 signature/draft_dir/files_count
  - 对 hook+file 平台检查 signature/data_dir/draft_dir/hooks
  - 输出: 5 平台统一 dashboard + JSON
  - 退出码: 0=全绿 1=有 RED
  - 写入: system/run/platform-dashboard.md
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

CST = timezone(timedelta(hours=8))
PLATFORMS_YAML = Path("system/platforms.yaml")
DASHBOARD_MD = Path("system/run/platform-dashboard.md")
LEDGER_PATH = Path(".sync/state/platform-health.jsonl")
HUB_ROOT_DEFAULT = r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub"
LAUNCHER = Path("hub-engine/scripts/hub_mcp_launcher.py")


def _load_platforms(hub_root):
    p = hub_root / PLATFORMS_YAML
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        return d.get("platforms", {})
    except (OSError, yaml.YAMLError) as exc:
        print("platforms.yaml 读取失败: " + str(exc), file=sys.stderr)
        return {}


def check_mcp_platform(name, info, hub_root):
    """检查 mcp 平台: launcher + args + python."""
    result = {
        "platform": name,
        "type": info["type"],
        "checks": {},
        "status": "GREEN",
        "issues": [],
    }
    cfg = Path(info["mcp_config_path"])
    if not cfg.is_absolute():
        cfg = Path.home() / cfg
    if not cfg.is_file():
        result["checks"]["config"] = "MISSING"
        result["issues"].append("config 缺失: " + str(cfg))
        result["status"] = "RED"
        return result
    result["checks"]["config"] = "OK (" + cfg.name + ")"
    try:
        if info.get("config_format") == "yaml":
            with open(cfg, encoding="utf-8") as fh:
                d = yaml.safe_load(fh)
            servers = d.get("mcp_servers", d.get("mcpServers", {}))
        else:
            with open(cfg, encoding="utf-8") as fh:
                d = json.load(fh)
            servers = d.get("mcpServers", d.get("mcp_servers", {}))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        result["checks"]["parse"] = "FAIL: " + str(exc)
        result["issues"].append("config 解析失败: " + str(exc))
        result["status"] = "RED"
        return result
    amh = servers.get("agent_memory_hub") or servers.get("agent-memory-hub")
    if not amh:
        result["checks"]["server"] = "MISSING"
        result["issues"].append("agent_memory_hub server 块未注册")
        result["status"] = "RED"
        return result
    args = amh.get("args", [])
    if not args:
        result["checks"]["args"] = "EMPTY"
        result["issues"].append("args 为空")
        result["status"] = "RED"
        return result
    result["checks"]["args"] = "OK (" + str(len(args)) + " 项)"
    if "launcher" not in str(args[0]).lower():
        result["checks"]["launcher"] = "OLD"
        result["issues"].append("args[0] 未用 launcher: " + str(args[0]))
        result["status"] = "YELLOW"
    else:
        result["checks"]["launcher"] = "OK"
    cmd = amh.get("command", "")
    if cmd and not Path(cmd).is_file():
        result["checks"]["python"] = "MISSING: " + str(cmd)
        result["issues"].append("python 路径不存在: " + str(cmd))
        result["status"] = "RED"
    else:
        result["checks"]["python"] = "OK" if cmd else "N/A"
    return result


def check_file_platform(name, info, hub_root):
    """检查 file 平台: signature + draft_dir + files_count."""
    result = {
        "platform": name,
        "type": info["type"],
        "checks": {},
        "status": "GREEN",
        "issues": [],
    }
    key_path = hub_root / info.get("key_path", "")
    if not key_path.is_file():
        result["checks"]["signature"] = "MISSING"
        result["issues"].append("签名 key 缺失: " + str(key_path))
        result["status"] = "RED"
    else:
        result["checks"]["signature"] = "OK"
    draft_dir = hub_root / info.get("draft_dir", "")
    if not draft_dir.is_dir():
        result["checks"]["draft_dir"] = "MISSING"
        result["issues"].append("草稿目录不存在: " + str(draft_dir))
        result["status"] = "RED"
    else:
        file_count = sum(
            1 for f in draft_dir.iterdir() if f.is_file() and f.suffix == ".md"
        )
        result["checks"]["draft_dir"] = "OK (" + str(file_count) + " 张草稿)"
        result["checks"]["files_count"] = file_count
    return result


def check_hook_file_platform(name, info, hub_root):
    """检查 hook+file 平台: signature + data_dir + draft_dir."""
    result = check_file_platform(name, info, hub_root)
    data_dir = Path(info.get("data_dir", ""))
    if not data_dir.is_absolute():
        data_dir = Path.home() / data_dir
    if not data_dir.is_dir():
        result["checks"]["data_dir"] = "MISSING: " + str(data_dir)
        result["issues"].append("data_dir 不存在: " + str(data_dir))
        if result["status"] == "GREEN":
            result["status"] = "YELLOW"
    else:
        result["checks"]["data_dir"] = "OK"
    return result


def run_healthcheck(hub_root):
    platforms = _load_platforms(hub_root)
    results = []
    for name, info in platforms.items():
        t = info.get("type", "")
        if t == "mcp":
            results.append(check_mcp_platform(name, info, hub_root))
        elif t == "file":
            results.append(check_file_platform(name, info, hub_root))
        elif t == "hook+file":
            results.append(check_hook_file_platform(name, info, hub_root))
    return results


def _status_icon(s):
    return {"GREEN": "✅", "YELLOW": "🟡", "RED": "❌"}.get(s, "?")


def _local_now_iso():
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M")


def write_dashboard(results, hub_root):
    out = hub_root / DASHBOARD_MD
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 5 平台健康 Dashboard",
        "生成时间 " + _local_now_iso() + " (CST)",
        "",
        "## 总体",
        "  GREEN: "
        + str(sum(1 for r in results if r["status"] == "GREEN"))
        + " / "
        + str(len(results)),
        "  YELLOW: " + str(sum(1 for r in results if r["status"] == "YELLOW")),
        "  RED: " + str(sum(1 for r in results if r["status"] == "RED")),
        "",
        "## 平台详情",
        "",
    ]
    for r in results:
        lines.append(
            "### "
            + _status_icon(r["status"])
            + " "
            + r["platform"]
            + " ("
            + r["type"]
            + ")"
        )
        for ck, val in r["checks"].items():
            lines.append("  - " + ck + ": " + str(val))
        if r["issues"]:
            lines.append("  - issues:")
            for iss in r["issues"]:
                lines.append("    - " + iss)
        lines.append("")
    lines.append("---")
    lines.append("由 platform_healthcheck.py 自动生成 - 每日 7:55 cron")
    out.write_text("\n".join(lines), encoding="utf-8")
    print("dashboard 已写: " + str(out))


def main():
    hub_root = Path(os.environ.get("HUB_ROOT", HUB_ROOT_DEFAULT))
    if not hub_root.is_dir():
        print("hub_root 不存在: " + str(hub_root), file=sys.stderr)
        return 2
    results = run_healthcheck(hub_root)
    print("=== 5 平台统一健康检查 ===")
    for r in results:
        icon = _status_icon(r["status"])
        print(
            "  " + icon + " " + r["platform"] + " (" + r["type"] + "): " + r["status"]
        )
        for iss in r["issues"]:
            print("    - " + iss)
    write_dashboard(results, hub_root)
    ledger = hub_root / LEDGER_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "results": [
            {"platform": r["platform"], "status": r["status"]} for r in results
        ],
    }
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    red_count = sum(1 for r in results if r["status"] == "RED")
    return 1 if red_count else 0


if __name__ == "__main__":
    sys.exit(main())
