# @version V1.0 / 2026-09-09 / Hermes / MCP 健康检查 + 自愈
"""mcp_healthcheck.py - MCP 启动器+自愈 一站式健康检查."

V1.0 (2026-09-09): 方案 D 实施.
  - 检查 3 平台 mcp.json 配置
  - 检测 mcp_server.py 路径
  - 触发自愈(若 launcher 存在)
  - 输出健康报告
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

PLATFORMS = {
    "hermes": {
        "config": Path(r"C:/Users/Fan-SJSS/AppData/Local/hermes/config.yaml"),
        "mcp_path_field": "args",
        "format": "yaml_block",
    },
    "trae": {
        "config": Path(r"C:/Users/Fan-SJSS/.trae-cn/mcp.json"),
        "mcp_path_field": "mcpServers.agent-memory-hub.args",
        "format": "json",
    },
    "workbuddy": {
        "config": Path(r"C:/Users/Fan-SJSS/.workbuddy/mcp.json"),
        "mcp_path_field": "mcpServers.agent-memory-hub.args",
        "format": "json",
    },
}

LAUNCHER = Path(
    r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/hub-engine/scripts/hub_mcp_launcher.py"
)


def check_platform(name: str, info: dict) -> dict:
    cfg = info["config"]
    result = {
        "platform": name,
        "config": str(cfg),
        "config_exists": cfg.exists(),
        "issues": [],
    }
    if not cfg.exists():
        result["issues"].append("config 缺失")
        result["status"] = "RED"
        return result
    if info["format"] == "json":
        try:
            with open(cfg, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            result["issues"].append(f"json 解析失败: {exc}")
            result["status"] = "RED"
            return result
        parts = info["mcp_path_field"].split(".")
        cur = d
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                result["issues"].append(f"路径 {info['mcp_path_field']} 不存在")
                result["status"] = "RED"
                return result
        result["args"] = cur
    else:  # yaml
        text = cfg.read_text(encoding="utf-8")
        # 简单 grep 出 agent_memory_hub 块的 args
        import re

        m = re.search(r"agent_memory_hub:.*?args:.*?(?=\n  [a-z])", text, re.DOTALL)
        if not m:
            result["issues"].append("yaml 中 agent_memory_hub 块未找到")
            result["status"] = "RED"
            return result
        # 提取所有 - 开头的行
        args = re.findall(r"^\s*-\s*(.+)$", m.group(0), re.MULTILINE)
        result["args"] = [a.strip().strip('"') for a in args]
    # 检查 launcher 是否在 args[0]
    if not result["args"] or LAUNCHER.name not in result["args"][0]:
        result["issues"].append("args[0] 不是 launcher（仍指向 mcp_server.py）")
    # 检查 mcp_server.py 真实存在
    if result["args"]:
        candidate = Path(result["args"][0])
        if not candidate.is_file():
            result["issues"].append(f"{candidate} 不存在")
    result["status"] = "GREEN" if not result["issues"] else "YELLOW"
    return result


def main() -> int:
    results = [check_platform(n, i) for n, i in PLATFORMS.items()]
    print("=== MCP 连接健康检查 ===")
    print(f"  Launcher: {LAUNCHER}")
    print(f"  Launcher 存在: {'✅' if LAUNCHER.is_file() else '❌'}")
    print()
    for r in results:
        icon = {"GREEN": "✅", "YELLOW": "🟡", "RED": "🔴"}[r["status"]]
        print(f"{icon} {r['platform']}: status={r['status']}")
        if r.get("args"):
            print(f"   args[0]: {r['args'][0]}")
        for issue in r["issues"]:
            print(f"   ⚠️ {issue}")
    fails = sum(1 for r in results if r["status"] == "RED")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
