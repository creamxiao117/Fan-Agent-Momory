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

from scripts.capability_reconcile import budgets, main, ratchet, reconcile, render


def _hub(
    tmp_path: Path,
    *,
    declare_mcp: str | None,
    declare_skills: str | None,
    ratchet_tokens: int = 0,
    target_tokens: int = 0,
) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    glob: dict = {}
    cap: dict = {}
    if ratchet_tokens:
        cap["per_platform_ratchet"] = {"trae": ratchet_tokens}
    if target_tokens:
        cap["per_session_target"] = target_tokens
    if cap:
        glob["capability_budget"] = cap
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


def test_per_platform_ratchet_is_hard(tmp_path):
    """逐平台棘轮超限 = 硬约束（且提示"降级能力"而非"改基线"）。

    为什么不是「全平台求和帽」：那是错误的量——各客户端各付各的，求和约束不了任何会话。
    """
    mcp = tmp_path / "mcp.json"
    mcp.write_text('{"mcpServers": {"a": {}, "b": {}}}', encoding="utf-8")
    hub = _hub(tmp_path, declare_mcp=str(mcp), declare_skills=None, ratchet_tokens=100)
    (hub / "system" / "capabilities.json").write_text(
        '{"mcp": {"trae": [{"server": "a"}, {"server": "b"}]}, "skills": {}}', encoding="utf-8"
    )
    assert ratchet(hub) == {"trae": 100}
    r = reconcile(hub)
    # 两个 MCP server × 200 token = 400 > 100
    assert [d["platform"] for d in r["over_ratchet"]] == ["trae"]
    assert r["fleet_tokens"] == 400  # 求和只作库存参考，**不参与判定**
    assert "不得改基线" in render(r)


def test_soft_target_reports_but_does_not_block(tmp_path):
    """软目标超限 → **只报不拦**（带具体降级候选）；否则会训练出 --no-verify。"""
    mcp = tmp_path / "mcp.json"
    mcp.write_text('{"mcpServers": {"a": {}}}', encoding="utf-8")
    hub = _hub(tmp_path, declare_mcp=str(mcp), declare_skills=None, target_tokens=100)
    (hub / "system" / "capabilities.json").write_text(
        '{"mcp": {"trae": [{"server": "a"}]}, "skills": {}}', encoding="utf-8"
    )
    assert budgets(hub)["per_session_target"] == 100
    r = reconcile(hub)
    assert not r["over_ratchet"]  # 未登记棘轮 ⇒ 不构成硬失败
    assert r["over_target"] and r["over_target"][0]["over"] == 100  # 200 - 100
    assert "降级候选" in render(r)
    assert main(["--root", str(hub)]) == 0  # 软目标不改变退出码


def test_missing_product_does_not_crash(tmp_path):
    """产物未渲染时不得崩（首次接入/换机场景）。"""
    hub = _hub(tmp_path, declare_mcp=None, declare_skills=None)
    r = reconcile(hub)
    assert r["matched"] == ["trae"]
