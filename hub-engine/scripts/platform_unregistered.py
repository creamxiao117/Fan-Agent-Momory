# @version V1.0 / 2026-09-15 / Hermes / 未接入平台候选扫描（对照 platforms.yaml）
"""platform_unregistered.py — 列出"本机存在 MCP 配置、但未在 system/platforms.yaml 登记"的 Agent 平台。

用途（A/3）：新平台装好后很容易被遗忘接入；本脚本做提示级扫描，便于一键补登（补登后跑 A/2 三步流程）。
输出：每行一个候选平台；--json 输出结构化结果；**退出码恒为 0**（纯信息级，不阻断巡检）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_HUB_DEFAULT = r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub"

# 候选位置（相对 HOME）：覆盖 trae/codex/workbuddy/cursor/claude/gemini/qwen/windsurf/vscode/continue/opencode 等
_CANDIDATES = (
    ".trae/mcp.json",
    ".trae-cn/mcp.json",
    ".codex/config.toml",
    ".workbuddy/mcp.json",
    ".cursor/mcp.json",
    ".claude.json",
    ".claude/mcp.json",
    ".gemini/settings.json",
    ".qwen/settings.json",
    ".windsurf/mcp.json",
    ".vscode/mcp.json",
    ".continue/config.json",
    ".opencode/config.json",
    ".kilo/mcp.json",
    ".roo/mcp.json",
    ".lingma/mcp.json",
    ".iflow/mcp.json",
    "AppData/Local/hermes/config.yaml",
)


def _has_mcp_block(path: Path) -> bool:
    """尽力解析（json/yaml/toml）判断是否含 MCP 服务块；不认识的格式返回 False。"""
    name = path.name.lower()
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    try:
        if name.endswith((".toml",)):
            import tomllib

            data = tomllib.loads(raw.decode("utf-8", "replace"))
        elif name.endswith((".yaml", ".yml")):
            data = yaml.safe_load(raw.decode("utf-8", "replace"))
        else:
            data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    for key in ("mcpServers", "mcp_servers", "servers"):
        block = data.get(key)
        if isinstance(block, dict) and block:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    hub = Path(_HUB_DEFAULT)
    as_json = "--json" in argv
    if "--root" in argv:
        hub = Path(argv[argv.index("--root") + 1])

    declared: set[str] = set()
    p = hub / "system" / "platforms.yaml"
    if p.is_file():
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            declared = set((data.get("platforms") or {}).keys())
            # 已登记平台的配置路径也算"已接入"，避免同名文件被重复提示
            declared |= {
                Path(str(info.get("mcp_config_path", ""))).name
                for info in (data.get("platforms") or {}).values()
                if isinstance(info, dict) and info.get("mcp_config_path")
            }
        except Exception as exc:
            print(f"[unregistered] platforms.yaml 读取失败: {exc}", file=sys.stderr)

    home = Path.home()
    found = []
    for rel in _CANDIDATES:
        cfg = home / rel
        if not cfg.is_file():
            continue
        if cfg.name in declared or rel.split("/")[0].lstrip(".") in {
            d.lstrip(".") for d in declared
        }:
            continue
        if _has_mcp_block(cfg):
            found.append({"platform_hint": rel.split("/")[0], "config": str(cfg)})

    if as_json:
        print(
            json.dumps(
                {"declared": sorted(declared), "unregistered": found},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("=== 未接入平台候选（存在 MCP 块但未登记 platforms.yaml）===")
        if not found:
            print("  ✅ 无候选：本机未发现未登记的 MCP 配置")
        for item in found:
            print(f"  • {item['platform_hint']:20} {item['config']}")
        if found:
            print(
                "  提示：登记到 system/platforms.yaml 后跑 platform_sync.py --apply + platform_healthcheck.py"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
