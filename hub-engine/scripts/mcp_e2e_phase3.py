"""MCP E2E 测试脚本 —— stdio 启动 mcp_server.py + 调 list_tools / call_tool

V1.0 (2026-09-08): T11 Phase 3 E2E —— 验证 hub_announce 注册到 MCP list_tools。
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HUB_ROOT = ROOT / "AgentMemoryHub"
MCP_SERVER = ROOT / "hub-engine" / "mcp_server.py"

async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER), "--root", str(HUB_ROOT)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # list_tools
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"tools: {tool_names}")
            assert "hub_announce" in tool_names, f"hub_announce missing: {tool_names}"

            # call_tool hub_announce
            res = await session.call_tool(
                "hub_announce",
                arguments={
                    "platform": "hermes",
                    "action": "phase3_e2e_test",
                    "payload": {"commit": "phase3_done"},
                },
            )
            print(f"hub_announce result: {res.content[0].text if res.content else res}")

            print("E2E OK")


if __name__ == "__main__":
    asyncio.run(main())