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


def test_search_and_bootstrap_schemas_expose_compress_level(tmp_path):
    """任务1：schema 必须声明 compress_level，否则各平台 Agent 无法按协议传该参数"""
    from mcp_server import BOOTSTRAP_SCHEMA, SEARCH_SCHEMA

    assert "compress_level" in SEARCH_SCHEMA["properties"]
    assert "compress_level" in BOOTSTRAP_SCHEMA["properties"]


def test_call_tool_search_compress_level_passthrough(tmp_path):
    """任务1：hub_search 经 MCP session 透传 compress_level，返回压缩后的正文"""
    from mcp_server import build_server

    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [dll-lock]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\n"
        "# DLL 锁定规则\n"
        "这是首段导语，用于保留。\n"
        "## 实现细节\n"
        "这段细节正文应在级别五压缩时被丢弃。\n",
        encoding="utf-8",
    )
    server = build_server(tmp_path)

    async def _call():
        async with create_connected_server_and_client_session(server) as session:
            return await session.call_tool(
                "hub_search",
                {
                    "query": "dll-lock",
                    "include_body": True,
                    "compress_level": 5,
                    "platform": "trae",
                },
            )

    res = asyncio.run(_call())
    payload = json.loads(res.content[0].text)
    assert payload["ok"] is True
    body = payload["hits"][0]["body"]
    assert "首段导语" in body  # 摘要模式保留题后首段
    assert "这段细节" not in body  # level5 丢弃 ## 后细节


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
