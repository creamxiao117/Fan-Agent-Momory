# @version V1.0 / 2026-11-03 / pi / MCP ui 资源声明的「按客户端」行为
"""**按客户端决定是否声明 ui:// 资源**（2026-11-03 实测）。

背景
----
- **WorkBuddy**（MCP Apps 宿主）：**需要** `_meta.ui.resourceUri` 才能把工具放进 liveApps 目录
  （缺了 ⇒ `missing_ui_resourceUri` ⇒ **Agent 调不了这些工具** ⇒ 检索不留痕）。
- **pi**：自己也起 MCP-App 会话服务器（`127.0.0.1:8377` 起连续端口）并用**系统浏览器**渲染
  ⇒ **每调一次中枢工具就弹一个浏览器窗口**（用户实测：不启动 WorkBuddy 也弹）；
  而 pi 官方文档明确「Pi does not render MCP App resources」⇒ 对 pi 而言这些 ui:// **零价值**。

⇒ 默认（`auto`）：**只给 workbuddy 声明**；其它客户端一律不声明。
"""

from mcp_server import _client_kind, _ui_enabled, _ui_meta


def test_auto_mode_only_declares_for_workbuddy():
    assert _ui_enabled("workbuddy") is True
    assert _ui_enabled("pi") is False
    assert _ui_enabled("hermes") is False
    assert _ui_enabled("unknown") is False


def test_env_override_on_off(monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_HUB_MCP_UI", "on")
    assert _ui_enabled("pi") is True
    monkeypatch.setenv("AGENT_MEMORY_HUB_MCP_UI", "off")
    assert _ui_enabled("workbuddy") is False
    monkeypatch.delenv("AGENT_MEMORY_HUB_MCP_UI")
    assert _ui_enabled("workbuddy") is True


def test_ui_meta_empty_for_pi():
    """pi：不声明 ui ⇒ tools/list 里没有 ui 资源 ⇒ 客户端不会去渲染 ⇒ **不弹窗**。"""
    assert _ui_meta("ui://agent-memory-hub/hub_search.html", "pi") == {}


def test_ui_meta_has_uri_and_surface_for_workbuddy():
    meta = _ui_meta("ui://agent-memory-hub/hub_search.html", "workbuddy")
    assert meta["ui"]["resourceUri"] == "ui://agent-memory-hub/hub_search.html"
    assert meta["workbuddy"]["ui"]["launchSurface"] in {"inline", "panel"}


def test_client_kind_detects_explicit_and_env(monkeypatch):
    assert _client_kind("pi") == "pi"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", "/tmp/pi")
    assert _client_kind(None) == "pi"
    monkeypatch.delenv("PI_CODING_AGENT_DIR")
    monkeypatch.setenv("WORKBUDDY_HOME", "/tmp/wb")
    assert _client_kind(None) == "workbuddy"


def test_server_tools_list_has_no_ui_for_pi(tmp_path):
    """端到端：pi 客户端拿到的 tools/list **不含** ui 资源。"""
    import asyncio

    from mcp_session import memory_session

    from mcp_server import build_server

    async def _list():
        server = build_server(tmp_path, client="pi")
        async with memory_session(server) as client:
            res = await client.list_tools()
            return res.tools

    tools = asyncio.run(_list())
    assert tools
    for t in tools:
        assert not (t.meta or {}).get("ui"), f"{t.name} 不应向 pi 声明 ui 资源"
