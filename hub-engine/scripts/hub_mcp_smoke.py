# @version V1.0 / 2026-10-02 / pi / MCP 端到端冒烟：握手 → tools/list → hub_search 实调
"""MCP 冒烟（`hub_mcp_smoke`）——不依赖任何平台客户端，直接用 SDK 起 stdio server。

用途：①接通后验证「解释器 + mcp_server + 中枢根」三者可用；②回归用（G2 检查项）。
退出码：0 = 全部通过；1 = 有步骤失败。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))


async def _smoke(python: str, server: Path, root: Path, query: str) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=python,
        args=[str(server), "--root", str(root)],
    )
    failures: list[str] = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        # SDK 2.x 用 server_info（snake_case）；1.x 用 serverInfo —— 两版都容忍
        info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
        name = getattr(info, "name", "?") if info else "?"
        ver = getattr(info, "version", "?") if info else "?"
        print(f"[PASS] initialize :: server={name} v{ver}")
        tools = await session.list_tools()
        names = sorted(t.name for t in tools.tools)
        print(f"[PASS] tools/list :: {len(names)} 个 -> {', '.join(names)}")
        expected = {
            "hub_search",
            "hub_get",
            "hub_index",
            "hub_bootstrap",
            "hub_ingest_candidate",
        }
        missing = expected - set(names)
        if missing:
            failures.append(f"缺少必需工具: {sorted(missing)}")

        res = await session.call_tool("hub_search", {"query": query, "platform": "pi"})
        # SDK 2.x: structured_content；1.x: structuredContent；本服务实际走 TextContent(JSON)
        payload = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None) or {}
        if not payload:
            import json

            for item in getattr(res, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    try:
                        payload = json.loads(text)
                        break
                    except ValueError:
                        continue
        hits = payload.get("hits", [])
        if payload.get("ok") and hits:
            print(f"[PASS] hub_search :: 命中 {len(hits)} 张，首张 = {hits[0]['rel_path']}")
            print(f"       审计 id = {payload.get('audit_id')} channel = {payload.get('channel')}")
        else:
            failures.append(f"hub_search 无命中: {str(res.content)[:200]}")
    for f in failures:
        print(f"[FAIL] {f}")
    print(f"\n=== MCP 冒烟：{'PASS' if not failures else 'FAIL'} ===")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MCP stdio 端到端冒烟")
    ap.add_argument("--python", default=sys.executable, help="跑 mcp_server 的解释器")
    ap.add_argument("--server", default=str(_HUB_ENGINE / "mcp_server.py"))
    ap.add_argument("--root", default=str(_HUB_ENGINE.parent / "AgentMemoryHub"))
    ap.add_argument("--query", default="dll 版本锁")
    args = ap.parse_args(argv)
    return asyncio.run(_smoke(args.python, Path(args.server), Path(args.root), args.query))


if __name__ == "__main__":
    sys.exit(main())
