# @version V1.0 / 2026-11-04 / pi / MCP 调用的 platform 归因
"""**MCP 调用的 platform 归因**（2026-11-04）。

背景
----
调用方（pi 等）通常**不传** `platform` ⇒ 审计记 `platform="unknown"`
⇒ 「按平台」的检索/复用口径**看不见 MCP 流量**（pi 的调用全落 unknown；
`experience/pi-as-sixth-platform-three-layer-templat` 第 8 条要求「检索要可观测、带 platform」）。

⇒ 缺省按**已识别的客户端**填 platform（客户端名 == 平台名，见 `hub.config.yaml`）；
  **认不出的客户端不猜**（保持 unknown）。

⚠️ 只给**接受 platform 参数**的工具补 ⇒ `hub_safe_patch` 没有这个参数，
  无脑塞会 TypeError（本文件第 4 个用例守住这条）。
"""

import asyncio  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# tests/ 是包（tests/__init__.py 存在）⇒ pytest 只把**根目录**放进 sys.path，
# 不放 tests/ ⇒ 直接 `from mcp_session import ...` 依赖别的测试文件先跑（顺序依赖）。
# 本文件自己把 tests/ 加进去 ⇒ **单跑也能过**（顺序依赖是「假绿/假红」的一种）。
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from mcp_session import memory_session  # noqa: E402

import mcp_server  # noqa: E402


def _call(monkeypatch, tmp_path, tool: str, args: dict, client: str = "pi") -> dict:
    """起一个内存会话调工具，返回 handler 收到的 kwargs。"""
    captured: dict = {}

    def fake(root, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setitem(mcp_server.HANDLERS, tool, fake)

    async def _run():
        server = mcp_server.build_server(tmp_path, client=client)
        async with memory_session(server) as session:
            await session.call_tool(tool, args)

    asyncio.run(_run())
    return captured


def test_pi_client_fills_platform(monkeypatch, tmp_path):
    got = _call(monkeypatch, tmp_path, "hub_search", {"query": "x"}, client="pi")
    assert got.get("platform") == "pi"


def test_explicit_platform_wins(monkeypatch, tmp_path):
    got = _call(monkeypatch, tmp_path, "hub_search", {"query": "x", "platform": "workbuddy"}, client="pi")
    assert got.get("platform") == "workbuddy"


def test_unknown_client_stays_unknown(monkeypatch, tmp_path):
    """认不出的客户端**不猜**（保持 unknown，而不是瞎填一个平台）。"""
    got = _call(monkeypatch, tmp_path, "hub_search", {"query": "x"}, client="some-other-client")
    assert got.get("platform") == "unknown"


def test_tool_without_platform_param_is_not_given_one(monkeypatch, tmp_path):
    """`hub_safe_patch` 不接受 platform ⇒ 不得无脑塞（否则 TypeError）。"""
    got = _call(
        monkeypatch,
        tmp_path,
        "hub_safe_patch",
        {"path": "a.md", "old_string": "x", "new_string": "y"},
        client="pi",
    )
    assert "platform" not in got
