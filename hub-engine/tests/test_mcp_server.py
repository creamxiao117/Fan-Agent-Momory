import asyncio
import json

import pytest

try:
    from mcp.shared.memory import create_connected_server_and_client_session

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

pytestmark = pytest.mark.skipif(not HAS_MCP, reason="mcp 未安装")


def test_build_server_exposes_tools(tmp_path):
    from mcp_server import build_server

    server = build_server(tmp_path)

    async def _list():
        async with create_connected_server_and_client_session(server) as session:
            res = await session.list_tools()
            return {t.name for t in res.tools}

    names = asyncio.run(_list())
    assert names == {
        "hub_search",
        "hub_get",
        "hub_index",
        "hub_bootstrap",
        "hub_ingest_candidate",
    }


def test_call_tool_search(tmp_path):
    from mcp_server import build_server

    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [dll-lock]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    server = build_server(tmp_path)

    async def _call():
        async with create_connected_server_and_client_session(server) as session:
            return await session.call_tool(
                "hub_search", {"query": "dll-lock", "platform": "trae"}
            )

    res = asyncio.run(_call())
    payload = json.loads(res.content[0].text)
    assert payload["ok"] is True
    assert payload["hits"][0]["slug"] == "dll-lock"
