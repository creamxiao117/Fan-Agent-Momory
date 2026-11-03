import asyncio
import json

# 2026-11-02：本机 mcp 2.2.0 没有 `create_connected_server_and_client_session` ⇒
# 原 try/except 把**整个文件静默 skip**（MCP server 零覆盖且 CI 全绿）。
# ⇒ 改用兼容夹具 tests/mcp_session.py（新版用原生 helper，旧版自己接内存流）。
import sys as _sys
from pathlib import Path as _Path

import pytest

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from mcp_session import memory_session

HAS_MCP = True

pytestmark = pytest.mark.skipif(not HAS_MCP, reason="mcp 未安装")


def test_build_server_exposes_tools(tmp_path):
    from mcp_server import build_server

    server = build_server(tmp_path)

    async def _list():
        async with memory_session(server) as session:
            res = await session.list_tools()
            return {t.name for t in res.tools}

    names = asyncio.run(_list())
    assert names == {
        "hub_search",
        "hub_get",
        "hub_index",
        "hub_bootstrap",
        "hub_ingest_candidate",
        "hub_announce",
        "hub_safe_patch",
    }


def test_tools_declare_launch_surface_inline(tmp_path):
    """**带 UI 资源的工具必须声明 `launchSurface=inline`**（否则 WorkBuddy 会开外部浏览器窗口）。

    回归背景（2026-11-02）：WorkBuddy 的 `resolveMcpAppSurface(toolMeta)` 读
    `toolMeta["workbuddy"]["ui"]["launchSurface"]`；不声明时走 hostDefault ⇒ 落到 sandbox 表面
    ⇒ **每次调用都弹一个浏览器窗口**（`http://127.0.0.1:8385/?session=…`）。
    合法值只有 `inline` / `panel`（WorkBuddy 的 `isSurface` 白名单）。

    注：2026-11-03 起 ui 资源**按客户端声明**（pi 不声明 ⇒ 不弹窗）⇒ 本用例用 workbuddy 客户端。
    """
    from mcp_server import build_server

    server = build_server(tmp_path, client="workbuddy")

    async def _list():
        async with memory_session(server) as session:
            res = await session.list_tools()
            return res.tools

    tools = asyncio.run(_list())
    with_ui = [t for t in tools if (t.meta or {}).get("ui", {}).get("resourceUri")]
    assert with_ui, "应至少有一个工具声明 UI 资源（WorkBuddy 目录校验需要）"
    for t in with_ui:
        meta = t.meta or {}
        assert meta.get("ui", {}).get("resourceUri"), t.name
        surface = (meta.get("workbuddy") or {}).get("ui", {}).get("launchSurface")
        assert surface in {"inline", "panel"}, f"{t.name} 的 launchSurface={surface!r}（非法值会被 WorkBuddy 忽略）"


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
        async with memory_session(server) as session:
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
        async with memory_session(server) as session:
            return await session.call_tool("hub_search", {"query": "dll-lock", "platform": "trae"})

    res = asyncio.run(_call())
    payload = json.loads(res.content[0].text)
    assert payload["ok"] is True
    assert payload["hits"][0]["slug"] == "dll-lock"
