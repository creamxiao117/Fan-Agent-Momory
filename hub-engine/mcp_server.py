"""hub-mcp-server：MCP stdio 入口，把中枢工具暴露给各 Agent 平台。

用法：python mcp_server.py --root <中枢根>  （或设环境变量 AGENT_MEMORY_HUB）
仅做协议转发，业务全部在 tools/mcp_handlers.py。
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证可 import tools.*

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

import tools.mcp_handlers as H

HANDLERS = {
    "hub_search": H.hub_search,
    "hub_get": H.hub_get,
    "hub_index": H.hub_index,
    "hub_bootstrap": H.hub_bootstrap,
    "hub_ingest_candidate": H.hub_ingest_candidate,
}

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "top_k": {"type": "integer"},
        "mode": {"type": "string"},
        "n": {"type": "integer"},
        "types": {"type": "array", "items": {"type": "string"}},
        "include_body": {"type": "boolean"},
        "compress_level": {"type": "integer"},
        "platform": {"type": "string"},
    },
    "required": ["query"],
}
GET_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "rel_path": {"type": "string"},
        "platform": {"type": "string"},
    },
}
INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "types": {"type": "array", "items": {"type": "string"}},
        "include_markdown": {"type": "boolean"},
        "platform": {"type": "string"},
    },
}
BOOTSTRAP_SCHEMA = {
    "type": "object",
    "properties": {
        "task_kind": {"type": "string"},
        "context": {"type": "string"},
        "platform": {"type": "string"},
        "top_k": {"type": "integer"},
        "include_body": {"type": "boolean"},
        "compress_level": {"type": "integer"},
    },
    "required": ["task_kind"],
}
INGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "type": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "slug": {"type": "string"},
    },
    "required": ["platform", "title", "body"],
}

# WorkBuddy MCP Apps 要求工具声明 UI 资源（_meta.ui.resourceUri）方可进入可用目录（liveApps）。
# 若不声明，catalog.refresh 会以 missing_ui_resourceUri 拒绝 → Agent 无法调用 → 检索不留痕。
_UI_META = {
    "hub_search": "ui://agent-memory-hub/hub_search.html",
    "hub_get": "ui://agent-memory-hub/hub_get.html",
    "hub_index": "ui://agent-memory-hub/hub_index.html",
    "hub_bootstrap": "ui://agent-memory-hub/hub_bootstrap.html",
    "hub_ingest_candidate": "ui://agent-memory-hub/hub_ingest_candidate.html",
}


def _normalize(name: str, arguments: dict) -> dict:
    """MCP 参数名（id/type）→ Python 参数名（id_/type_）"""
    args = dict(arguments)
    if name == "hub_get" and "id" in args:
        args["id_"] = args.pop("id")
    if name == "hub_ingest_candidate" and "type" in args:
        args["type_"] = args.pop("type")
    return args


def build_server(root: Path) -> Server:
    server = Server("agent-memory-hub")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name="hub_search",
                description="混合检索中枢（确定性+语义）",
                inputSchema=SEARCH_SCHEMA,
                _meta={"ui": {"resourceUri": _UI_META["hub_search"]}},
            ),
            Tool(
                name="hub_get",
                description="按 slug/路径读单张卡片全文",
                inputSchema=GET_SCHEMA,
                _meta={"ui": {"resourceUri": _UI_META["hub_get"]}},
            ),
            Tool(
                name="hub_index",
                description="浏览五类目录结构",
                inputSchema=INDEX_SCHEMA,
                _meta={"ui": {"resourceUri": _UI_META["hub_index"]}},
            ),
            Tool(
                name="hub_bootstrap",
                description="任务级引导：按 task_kind 分类检索生成引导块",
                inputSchema=BOOTSTRAP_SCHEMA,
                _meta={"ui": {"resourceUri": _UI_META["hub_bootstrap"]}},
            ),
            Tool(
                name="hub_ingest_candidate",
                description="候选回写（仅写 draft，不直写权威区）",
                inputSchema=INGEST_SCHEMA,
                _meta={"ui": {"resourceUri": _UI_META["hub_ingest_candidate"]}},
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"未知工具: {name}")
        res = handler(root, **_normalize(name, arguments or {}))
        return [TextContent(type="text", text=json.dumps(res, ensure_ascii=False))]

    @server.list_resources()
    async def _list_resources() -> list[Resource]:
        """WorkBuddy MCP Apps 要求 ui:// 资源可枚举（工具目录校验用）"""
        return [
            Resource(uri=uri, name=f"{name} 卡片") for name, uri in _UI_META.items()
        ]

    @server.read_resource()
    async def _read_resource(uri: str) -> str:
        """提供极简 HTML 占位页；WorkBuddy 打开资源视图时使用"""
        name = uri.rsplit("/", 1)[-1].removesuffix(".html") if uri else "hub"
        safe = "".join(c for c in name if c.isalnum() or c == "_")
        return f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{safe}</title><body style="font-family:system-ui;padding:16px">
<h2>Agent Memory Hub · {safe}</h2><p>此工具以文本响应为主，UI 资源仅供 WorkBuddy MCP Apps 目录展示。</p>
</body></html>"""

    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub-mcp-server")
    ap.add_argument("--root", help="中枢根目录；缺省读环境变量 AGENT_MEMORY_HUB")
    args = ap.parse_args(argv)
    root = args.root or os.environ.get("AGENT_MEMORY_HUB", "")
    if not root:
        print("需要 --root 或环境变量 AGENT_MEMORY_HUB", file=sys.stderr)
        return 2
    server = build_server(Path(root))

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
