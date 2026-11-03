"""hub-mcp-server：MCP stdio 入口，把中枢工具暴露给各 Agent 平台。

用法：python mcp_server.py --root <中枢根>  （或设环境变量 AGENT_MEMORY_HUB）
仅做协议转发，业务全部在 tools/mcp_handlers.py。
"""

import argparse
import asyncio
import json
import os
import sys
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证可 import tools.*

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

import tools.mcp_handlers as H

# === T3 PATCH REMOVED (2026-09-15): mcp SDK 2.0.0 原生支持 add_request_handler
# 旧 patch 假设新版 SDK 用装饰器风格（self.list_tools() 等），但 mcp 2.0.0 仍保留
# add_request_handler(method, params_type, handler) 三参数签名，无需 monkey-patch。


HANDLERS = {
    "hub_search": H.hub_search,
    "hub_get": H.hub_get,
    "hub_index": H.hub_index,
    "hub_bootstrap": H.hub_bootstrap,
    "hub_ingest_candidate": H.hub_ingest_candidate,
    "hub_announce": H.hub_announce,
    "hub_safe_patch": H.hub_safe_patch,
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
        # 规范参数（2026-10-02 口径统一）：light|code|hub|sync|project
        "task_tier": {"type": "string"},
        # deprecated 别名（dll|code|project|debug|ideation|generic），取值逐值锁定，
        # 解析入口唯一 = tools/task_tier.resolve_kind / scope_for
        "task_kind": {"type": "string"},
        "context": {"type": "string"},
        "platform": {"type": "string"},
        "top_k": {"type": "integer"},
        "include_body": {"type": "boolean"},
        "compress_level": {"type": "integer"},
    },
}
# 注意：**不再** required 任一字段 —— 两者都空等价旧 generic 宽范围（保持迁移前行为），
# 而 light 型由 handler 短路（skipped=true，不写审计）。
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

ANNOUNCE_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "description": "hermes/trae/code/workbuddy/dsh"},
        "action": {
            "type": "string",
            "description": "ingest_done / reset_warning / reconcile_done / ...",
        },
        "payload": {"type": "object", "description": "任意附加数据"},
    },
    "required": ["platform", "action"],
}

SAFE_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "old_string": {"type": "string"},
        "new_string": {"type": "string"},
        "replace_all": {"type": "boolean"},
        "dry_run": {"type": "boolean"},
    },
    "required": ["path", "old_string", "new_string"],
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

# ── launchSurface=inline（2026-11-02，实测消掉「每次调用都弹浏览器窗口」）─────
# 现象：WorkBuddy 每次调用上述工具，都会**用系统默认浏览器开一个新窗口**
#      （`http://127.0.0.1:8385/?session=…`，页面内容是本 MCP 的占位 UI，
#        页面自己写着「此工具以文本响应为主，UI 资源仅供 WorkBuddy MCP Apps 目录展示」）
#      ⇒ 用户侧就是「没事也弹网页窗口；连续调用就连续弹」。
# 根因（WorkBuddy 端代码，逆向确认）：
#   resolveMcpAppSurface(toolMeta) = readWorkBuddyUiMeta(toolMeta)?.launchSurface
#                                  ?? hostDefault ?? `inline`
#   readWorkBuddyUiMeta(meta)     = meta["workbuddy"]["ui"]["launchSurface"]
#   isSurface(v)                  = v === "inline" || v === "panel"
#   ⇒ 未声明时走 hostDefault（我们这个 app 不在 WorkBuddy 的「默认 panel」白名单里）
#     ⇒ 落到 **sandbox** 表面 ⇒ 外部浏览器窗口。
# 修法：**在工具 _meta 里显式声明 launchSurface=inline** ⇒ MCP App 内嵌在 WorkBuddy 界面，
#       不再开外部窗口；且 inline 的 app **不再被持久化成工作区产物**
#       （WorkBuddy：launchSurface===`inline` ⇒ skip publishArtifact / skip persist），
#       顺带少了「MCP App」产物污染工作区。
# 可用值仅 `inline` / `panel`（isSurface 白名单）；可用环境变量覆盖（默认 inline）。
_UI_SURFACE = os.environ.get("AGENT_MEMORY_HUB_MCP_UI_SURFACE", "inline").strip() or "inline"


def _client_kind(explicit: str | None = None) -> str:
    """识别调用方客户端（best-effort；识别不出就是 unknown）。"""
    if explicit:
        return explicit.strip().lower()
    if os.environ.get("PI_CODING_AGENT_DIR"):
        return "pi"
    if os.environ.get("WORKBUDDY_HOME") or os.environ.get("WORKBUDDY_SESSION_ID"):
        return "workbuddy"
    return "unknown"


# 默认**只给 WorkBuddy** 声明 ui:// 资源（它是唯一需要它们的 Apps 宿主）
UI_CLIENTS_DEFAULT: tuple[str, ...] = ("workbuddy",)


def _ui_enabled(client: str) -> bool:
    """本次是否声明 ui 资源。覆盖：`AGENT_MEMORY_HUB_MCP_UI=on|off|auto`（默认 auto）。"""
    mode = (os.environ.get("AGENT_MEMORY_HUB_MCP_UI") or "auto").strip().lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return client in UI_CLIENTS_DEFAULT


def _ui_meta(uri: str, client: str) -> dict:
    """工具 `_meta`：UI 资源声明 + **launchSurface=inline**（避免外部浏览器弹窗）。

    **按客户端决定是否声明**（2026-11-03 实测）：
      · WorkBuddy：需要 ui:// 才能进 liveApps 目录（缺了 ⇒ Agent 调不了 ⇒ 检索不留痕）⇒ 声明；
      · **pi**：自己也起 MCP-App 会话服务器（`127.0.0.1:8377` 起连续端口）并用**系统浏览器**渲染
        ⇒ 每调一次中枢工具就弹一个窗口；而 pi 官方文档明确「Pi does not render MCP App resources」
        ⇒ 对 pi 而言这些 ui:// **零价值** ⇒ **不声明**（不弹窗、不浪费）。
      · 其它客户端：默认不声明（保守：少声明总比多声明弹窗好）；需要时用环境变量强制打开。
    """
    if not _ui_enabled(client):
        return {}
    meta: dict = {"ui": {"resourceUri": uri}}
    if _UI_SURFACE in {"inline", "panel"}:
        meta["workbuddy"] = {"ui": {"launchSurface": _UI_SURFACE}}
    return meta


def _normalize(name: str, arguments: dict) -> dict:
    """MCP 参数名（id/type）→ Python 参数名（id_/type_）"""
    args = dict(arguments)
    if name == "hub_get" and "id" in args:
        args["id_"] = args.pop("id")
    if name == "hub_ingest_candidate" and "type" in args:
        args["type_"] = args.pop("type")
    return args


def build_server(root: Path, client: str | None = None) -> Server:
    client_kind = _client_kind(client)
    server = Server("agent-memory-hub")

    async def _list_tools(context, params) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name="hub_search",
                    description="混合检索中枢（确定性+语义）",
                    inputSchema=SEARCH_SCHEMA,
                    _meta=_ui_meta(_UI_META["hub_search"], client_kind),
                ),
                Tool(
                    name="hub_get",
                    description="按 slug/路径读单张卡片全文",
                    inputSchema=GET_SCHEMA,
                    _meta=_ui_meta(_UI_META["hub_get"], client_kind),
                ),
                Tool(
                    name="hub_index",
                    description="浏览五类目录结构",
                    inputSchema=INDEX_SCHEMA,
                    _meta=_ui_meta(_UI_META["hub_index"], client_kind),
                ),
                Tool(
                    name="hub_bootstrap",
                    description="任务级引导：按任务型（task_tier：light/code/hub/sync/project）分类检索生成引导块",
                    inputSchema=BOOTSTRAP_SCHEMA,
                    _meta=_ui_meta(_UI_META["hub_bootstrap"], client_kind),
                ),
                Tool(
                    name="hub_ingest_candidate",
                    description="候选回写（仅写 draft，不直写权威区）",
                    inputSchema=INGEST_SCHEMA,
                    _meta=_ui_meta(_UI_META["hub_ingest_candidate"], client_kind),
                ),
                Tool(
                    name="hub_announce",
                    description="跨平台公告：写一行到 .sync/announcements.jsonl（Phase 3 跨平台协调）",
                    inputSchema=ANNOUNCE_SCHEMA,
                ),
                Tool(
                    name="hub_safe_patch",
                    description="智能文件编辑：自动评估 patch 风险（≤3行走patch，≥4行走write_file），内置 ruff lint + 自动回滚",
                    inputSchema=SAFE_PATCH_SCHEMA,
                ),
            ]
        )

    async def _call_tool(context, params) -> CallToolResult:
        name = params.name
        arguments = dict(params.arguments or {})
        handler = HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"未知工具: {name}")
        res = handler(root, **_normalize(name, arguments))
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, ensure_ascii=False))])

    async def _list_resources(context, params) -> ListResourcesResult:
        """WorkBuddy MCP Apps 要求 ui:// 资源可枚举（工具目录校验用）"""
        return ListResourcesResult(resources=[Resource(uri=uri, name=f"{name} 卡片") for name, uri in _UI_META.items()])

    async def _read_resource(context, params) -> ReadResourceResult:
        """提供极简 HTML 占位页；WorkBuddy 打开资源视图时使用"""
        uri = params.uri
        name = uri.rsplit("/", 1)[-1].removesuffix(".html") if uri else "hub"
        safe = "".join(c for c in name if c.isalnum() or c == "_")
        html = f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{safe}</title><body style="font-family:system-ui;padding:16px">
<h2>Agent Memory Hub · {safe}</h2><p>此工具以文本响应为主，UI 资源仅供 WorkBuddy MCP Apps 目录展示。</p>
</body></html>"""
        return ReadResourceResult(contents=[TextResourceContents(uri=uri, mime_type="text/html", text=html)])

    server.add_request_handler("tools/list", PaginatedRequestParams, _list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, _call_tool)
    server.add_request_handler("resources/list", PaginatedRequestParams, _list_resources)
    server.add_request_handler("resources/read", ReadResourceRequestParams, _read_resource)
    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub-mcp-server")
    ap.add_argument("--root", help="中枢根目录；缺省读环境变量 AGENT_MEMORY_HUB")
    ap.add_argument("--client", default=None, help="调用方客户端（pi/workbuddy/…）；缺省按环境变量猜")
    args = ap.parse_args(argv)

    # 2026-10-21：stdio 通道的 stdout 也要显式钉死 UTF-8。
    # MCP SDK 的 stdio_server 虽用 UTF-8 包装了**协议帧**，但本进程其它 print
    # （含 traceback）走的是裸 stdout；Windows 中文环境下裸 stdout 默认 GBK，
    # 一旦有中文异常信息就会写出非 UTF-8 字节污染协议流。
    # 同口径见 rules/chinese-text-encoding-discipline（iron）：全链路钉死 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if _reconfigure is not None:
            with suppress(ValueError, OSError):
                _reconfigure(encoding="utf-8", errors="replace")

    root = args.root or os.environ.get("AGENT_MEMORY_HUB", "")
    if not root:
        print("需要 --root 或环境变量 AGENT_MEMORY_HUB", file=sys.stderr)
        return 2
    server = build_server(Path(root), client=args.client)

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
