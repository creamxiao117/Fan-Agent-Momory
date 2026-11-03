# @version V1.0 / 2026-11-02 / pi / MCP 内存会话夹具（本机 mcp 2.2.0 兼容层）
"""**in-memory MCP 会话**夹具（兼容 mcp 2.x）。

为什么需要它（2026-11-02 实测的假绿）
------------------------------------
`tests/test_mcp_server.py` 原来用 `from mcp.shared.memory import
create_connected_server_and_client_session` —— 但**本机装的 mcp 2.2.0 并没有这个导出**
（只有 `create_client_server_memory_streams`）⇒ 那个 `try/except ImportError` 把**整个文件
5 个用例静默 skip**了 ⇒ MCP server 的「工具清单 / 调用路径」长期**零覆盖**，而 CI 全绿。

⇒ 本模块提供**跨版本**的会话夹具：
  - 新版（≥2.3，有 `create_connected_server_and_client_session`）→ 直接用
  - 旧版（2.2.0 等，只有 streams）→ 自己把 ClientSession 与 Server 接到内存流上
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

try:  # 新版：一站式 helper
    from mcp.shared.memory import create_connected_server_and_client_session  # type: ignore

    HAS_NATIVE = True
except ImportError:  # 旧版（本机 mcp 2.2.0）：用 streams 自己接
    HAS_NATIVE = False


@asynccontextmanager
async def memory_session(server):
    """起一个连到 ``server`` 的内存 client session，产出 ``ClientSession``。"""
    if HAS_NATIVE:
        async with create_connected_server_and_client_session(server) as session:
            yield session
        return

    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    async with (
        create_client_server_memory_streams() as ((client_read, client_write), (server_read, server_write)),
        ClientSession(client_read, client_write) as client,
        anyio.create_task_group() as tg,
    ):

        async def _run_server():
            await server.run(server_read, server_write, server.create_initialization_options())

        tg.start_soon(_run_server)
        await client.initialize()
        try:
            yield client
        finally:
            tg.cancel_scope.cancel()


def run(coro):
    """在同步上下文里跑协程（测试用）。"""
    return asyncio.run(coro)
