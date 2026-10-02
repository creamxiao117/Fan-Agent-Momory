# @version V1.0 / 2026-10-02 / pi / 能力对账单测（M2/Task 17+18）
"""`capability_reconcile` 单测：声明态 vs 实测态必须能"抓撒谎"。

回归背景（为什么需要这个门禁）：
    能力的"期望"与"事实"此前**从未对过账**——唯一一份清单是手写快照卡。
    后果：登记了却没装（台账撒谎）、装了却没登记（换机必丢）都无人可见。
    本对账把两类差异变成不同级别：**声明了没装 = fail**（台账在撒谎），
    **装了没登记 = warn**（只是个隐患）。
"""

from pathlib import Path

import yaml

from scripts.capability_reconcile import budget, reconcile, render


def _hub(tmp_path: Path, *, declare_mcp: str | None, declare_skills: str | None, budget_tokens: int = 0) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    glob: dict = {}
    if budget_tokens:
        glob["capability_budget"] = {"max_discovery_tokens": budget_tokens}
    (hub / "hub.config.yaml").write_text(
        yaml.safe_dump(
            {
                "platforms": {
                    "trae": {
                        "type": "mcp",
                        "mcp_config_path": declare_mcp,
                        "skills_dir": declare_skills,
                    }
                },
                "platforms_global": glob,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return hub


def test_declared_but_absent_is_fail(tmp_path):
    """**登记了却没装 = fail**：台账撒谎必须红，而不是悄悄放过。"""
    hub = _hub(tmp_path, declare_mcp=str(tmp_path / "missing.json"), declare_skills=None)
    r = reconcile(hub)
    assert r["declared_only"] and "mcp_config_path" in r["declared_only"][0]["problems"][0]


def test_declared_and_present_is_matched(tmp_path):
    mcp = tmp_path / "mcp.json"
    mcp.write_text('{"mcpServers": {}}', encoding="utf-8")
    hub = _hub(tmp_path, declare_mcp=str(mcp), declare_skills=None)
    hub_sys = hub / "system"
    (hub_sys / "capabilities.json").write_text(
        '{"mcp": {"trae": [{"server": "x"}]}, "skills": {"trae": {"count": 0, "skills": []}}}',
        encoding="utf-8",
    )
    r = reconcile(hub)
    assert r["matched"] == ["trae"] and not r["declared_only"]


def test_actual_without_declaration_is_warn_not_fail(tmp_path):
    """**装了没登记 = warn**（隐患而非谎言）：它与 declared_only 必须分级不同。"""
    mcp = tmp_path / "mcp.json"
    mcp.write_text('{"mcpServers": {}}', encoding="utf-8")
    hub = _hub(tmp_path, declare_mcp=str(mcp), declare_skills=None)
    (hub / "system" / "capabilities.json").write_text(
        '{"mcp": {"trae": [], "ghost": [{"server": "y"}]}, "skills": {}}',
        encoding="utf-8",
    )
    r = reconcile(hub)
    assert [d["platform"] for d in r["actual_only"]] == ["ghost"]
    assert not r["declared_only"]


def test_budget_is_ratchet_semantics(tmp_path):
    """成本帽超限必须被标出（且提示"降级能力"而非"抬帽"）。"""
    mcp = tmp_path / "mcp.json"
    mcp.write_text('{"mcpServers": {"a": {}, "b": {}}}', encoding="utf-8")
    hub = _hub(tmp_path, declare_mcp=str(mcp), declare_skills=None, budget_tokens=100)
    (hub / "system" / "capabilities.json").write_text(
        '{"mcp": {"trae": [{"server": "a"}, {"server": "b"}]}, "skills": {}}', encoding="utf-8"
    )
    assert budget(hub) == 100
    r = reconcile(hub)
    # 两个 MCP server × 200 token = 400 > 100
    assert r["budget_over"] is True
    assert "不得抬帽" in render(r)


def test_missing_product_does_not_crash(tmp_path):
    """产物未渲染时不得崩（首次接入/换机场景）。"""
    hub = _hub(tmp_path, declare_mcp=None, declare_skills=None)
    r = reconcile(hub)
    assert r["matched"] == ["trae"]
