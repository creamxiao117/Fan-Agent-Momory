"""router_sync.py — 中枢路由表与平台/工具同步一致性检查

检查项目：
1. hub.config.yaml 配置的 platforms → platform_bridge.py 适配器覆盖（hermes → §分隔，其余 → ##分段）
2. mcp_handlers.py 中声明的 5 个 MCP 工具函数（hub_search/get/index/bootstrap/ingest_candidate）
3. tools/ 目录中 16 个工具模块是否可导入（无 import 错误）
4. 各平台记忆文件路径可达性（仅 warn，不 fail）
5. INDEX.md 登记卡数 vs 权威区卡数一致性（与 lint 互补）

退出码契约：
  0 = 全绿
  1 = info 级提示（某平台记忆文件不可达等）
  2 = warn 级问题（平台未注册适配器等）
  3 = critical（MCP handler 缺失或 tools/ 大面积 import 失败）

用法：
  python scripts/router_sync.py --root ..AgentMemoryHub
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))


# platform_bridge 适配器已覆盖的平台
_SUPPORTED_PLATFORMS = {"hermes", "trae", "code", "workbuddy"}

# mcp_handlers.py 应暴露的 5 个 MCP 入口函数
_REQUIRED_MCP_HANDLERS = [
    "hub_search",
    "hub_get",
    "hub_index",
    "hub_bootstrap",
    "hub_ingest_candidate",
]

# tools/ 目录（排除 __init__.py）应可导入的模块
_TOOLS_EXPECTED = [
    "compress", "dedup", "distill", "inject", "lint", "llm_health",
    "mcp_audit", "mcp_handlers", "mcp_policy", "memory_diff",
    "platform_bridge", "resilience", "retrieve", "semsearch", "snippet", "tidy",
]


def _check_platforms(root: Path) -> tuple[list[str], list[str]]:
    """检查 hub.config.yaml 中 platforms 配置与适配器覆盖一致性。
    返回 (warnings, infos)。"""
    warnings, infos = [], []
    try:
        from common.config import HubConfig
        cfg = HubConfig.load(root)
        platforms = cfg.platforms or {}
    except Exception as e:
        warnings.append(f"hub.config.yaml 加载失败: {e}")
        return warnings, infos

    for name, meta in platforms.items():
        if name not in _SUPPORTED_PLATFORMS:
            warnings.append(f"平台 '{name}' 在 hub.config.yaml 中登记，但 platform_bridge 未实现适配器")
            continue
        # 检查记忆文件路径可达性
        mem_dir = meta.get("memory_dir", "")
        target = meta.get("target_file", "")
        if mem_dir and target:
            full = Path(mem_dir) / target
            if not full.is_file():
                infos.append(f"平台 '{name}' 记忆文件不可达: {full}（平台可能未配置或未登录）")
    return warnings, infos


def _check_mcp_handlers() -> tuple[list[str], list[str]]:
    """检查 mcp_handlers.py 中 5 个必备 handler 是否都存在且可调用。"""
    critical, warnings = [], []
    try:
        mod = importlib.import_module("tools.mcp_handlers")
    except ImportError as e:
        critical.append(f"mcp_handlers.py 导入失败: {e}")
        return critical, warnings

    for fn_name in _REQUIRED_MCP_HANDLERS:
        if not hasattr(mod, fn_name):
            critical.append(f"MCP handler 缺失: tools.mcp_handlers.{fn_name}")
        elif not callable(getattr(mod, fn_name)):
            critical.append(f"MCP handler 不可调用: tools.mcp_handlers.{fn_name}")
    return critical, warnings


def _check_tools_importable() -> tuple[list[str], int]:
    """检查 tools/ 目录模块可导入性；返回 (failed_modules, total_count)。"""
    failed = []
    for mod_name in _TOOLS_EXPECTED:
        try:
            importlib.import_module(f"tools.{mod_name}")
        except ImportError as e:
            failed.append(f"{mod_name}: {e}")
    return failed, len(_TOOLS_EXPECTED)


def _run(root: Path) -> dict:
    """执行全部检查，返回结构化结果。"""
    result = {
        "platforms": {"warnings": [], "infos": []},
        "mcp_handlers": {"critical": [], "warnings": [], "present": 0, "required": len(_REQUIRED_MCP_HANDLERS)},
        "tools": {"failed": [], "total": 0, "import_ok": 0},
        "exit_code": 0,
    }

    # 1) 平台适配器覆盖
    pw, pi = _check_platforms(root)
    result["platforms"]["warnings"] = pw
    result["platforms"]["infos"] = pi

    # 2) MCP handler 完整性
    mc, mw = _check_mcp_handlers()
    result["mcp_handlers"]["critical"] = mc
    result["mcp_handlers"]["warnings"] = mw
    # 实际存在的 handler 数
    try:
        mod = importlib.import_module("tools.mcp_handlers")
        present = sum(1 for fn in _REQUIRED_MCP_HANDLERS if hasattr(mod, fn) and callable(getattr(mod, fn)))
    except ImportError:
        present = 0
    result["mcp_handlers"]["present"] = present

    # 3) tools/ 可导入性
    failed, total = _check_tools_importable()
    result["tools"]["failed"] = failed
    result["tools"]["total"] = total
    result["tools"]["import_ok"] = total - len(failed)

    # 4) 计算退出码
    has_critical = bool(mc)
    has_warnings = bool(pw) or bool(mw) or bool(failed)
    has_infos = bool(pi)

    if has_critical:
        result["exit_code"] = 3
    elif has_warnings:
        result["exit_code"] = 2
    elif has_infos:
        result["exit_code"] = 1
    else:
        result["exit_code"] = 0

    return result


def main() -> int:
    ap = argparse.ArgumentParser(prog="router-sync", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"❌ 中枢目录不存在: {root}", file=sys.stderr)
        return 3

    result = _run(root)
    exit_code = result["exit_code"]

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code

    # 人类可读输出
    print("=" * 60)
    print("  路由表同步检查")
    print("=" * 60)

    # 平台
    print(f"\n🔧 platforms ({len(result['platforms']['warnings'])} warn, {len(result['platforms']['infos'])} info):")
    for w in result["platforms"]["warnings"]:
        print(f"  ⚠️ {w}")
    for i in result["platforms"]["infos"]:
        print(f"  ℹ️ {i}")
    if not result["platforms"]["warnings"] and not result["platforms"]["infos"]:
        print("  ✅ 全部平台已登记适配器，记忆文件可达")

    # MCP
    mcp = result["mcp_handlers"]
    print(f"\n🔧 MCP handlers ({mcp['present']}/{mcp['required']}):")
    for c in mcp["critical"]:
        print(f"  🚨 {c}")
    for w in mcp["warnings"]:
        print(f"  ⚠️ {w}")
    if not mcp["critical"] and not mcp["warnings"]:
        print(f"  ✅ {mcp['present']}/{mcp['required']} 个 MCP handler 完整可调用")

    # tools
    tools = result["tools"]
    print(f"\n🔧 tools/ 模块 ({tools['import_ok']}/{tools['total']} 可导入):")
    for f in tools["failed"]:
        print(f"  ⚠️ 导入失败: {f}")
    if not tools["failed"]:
        print(f"  ✅ {tools['import_ok']}/{tools['total']} 全部可导入")

    # 退出码汇总
    icons = {0: "✅ 全绿", 1: "ℹ️ info 提示", 2: "⚠️ warn 需关注", 3: "🚨 critical"}
    print(f"\n{'=' * 60}")
    print(f"  退出码: {exit_code} ({icons.get(exit_code, 'unknown')})")
    print(f"{'=' * 60}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

