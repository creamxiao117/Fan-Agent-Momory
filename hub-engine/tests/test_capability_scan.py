# @version V1.0 / 2026-10-02 / pi / 能力实测态扫描单测（M0/Task 4）
"""`capability_scan` 单测：实测态读得对、产物可比对、失配必红（负样本先行）。

回归背景：平台能力清单此前只有一张**手写快照卡**（`methodology/agent-tool-inventory.md`），
必然过期。本模块把"实测态"做成渲染产物 + `--check`，故测试的重点是：
①读的是**平台配置本身**而不是任何转述；②磁盘产物与实测不一致时**必须红**。
"""

import json
from pathlib import Path

import yaml

from scripts.capability_scan import check, list_skills, render_markdown, scan, scan_cli, write_products


def _hub(tmp_path: Path) -> Path:
    """造一个中枢根：1 个 mcp 平台（带 json 配置）+ 1 个未登记 MCP 的平台。"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    mcp = tmp_path / "cli-mcp.json"
    mcp.write_text(
        json.dumps({"mcpServers": {"agent-memory-hub": {"command": "python", "args": ["x", "--root", "y"]}}}),
        encoding="utf-8",
    )
    skills = tmp_path / "skills"
    (skills / "alpha").mkdir(parents=True)
    (skills / "alpha" / "SKILL.md").write_text("# alpha\n", encoding="utf-8")
    (skills / "beta").mkdir(parents=True)
    (skills / "beta" / "SKILL.md").write_text("# beta\n", encoding="utf-8")
    (hub / "hub.config.yaml").write_text(
        yaml.safe_dump(
            {
                "platforms": {
                    "trae": {
                        "mcp_config_path": str(mcp),
                        "config_format": "json",
                        "skills_dir": str(skills),
                        "type": "mcp",
                    },
                    "bare": {"skills_dir": None, "mcp_config_path": None},
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return hub


def test_scan_reads_actual_client_config(tmp_path):
    """MCP 实测态必须来自**客户端配置文件本身**（不是任何转述/缓存）。"""
    hub = _hub(tmp_path)
    data = scan(hub)
    assert [r["server"] for r in data["mcp"]["trae"]] == ["agent-memory-hub"]
    assert data["mcp"]["trae"][0]["args_count"] == 3
    assert data["mcp"].get("bare", []) == [], "无 mcp_config_path 的平台不应出现在 MCP 实测态里"


def test_scan_skills_counts_skill_md_dirs(tmp_path):
    hub = _hub(tmp_path)
    data = scan(hub)
    assert data["skills"]["trae"]["count"] == 2
    assert data["skills"]["trae"]["skills"] == ["alpha", "beta"]
    assert data["skills"]["bare"]["count"] == 0


def test_list_skills_missing_dir_is_empty(tmp_path):
    assert list_skills(tmp_path / "nope") == []
    assert list_skills(None) == []


def test_cli_scan_finds_engine_subcommands():
    """本仓 CLI 面（engine 子命令）应被扫到——它是"能力"的第三类（MCP/Skill/CLI）。"""
    cli = scan_cli()
    assert "retrieve" in cli["engine_subcommands"]
    assert "tier-bootstrap" in cli["engine_subcommands"]
    assert len(cli["scripts_with_main"]) > 10


def test_render_markdown_mentions_platforms(tmp_path):
    hub = _hub(tmp_path)
    data = scan(hub)
    data["totals"] = {
        "platforms_registered": 2,
        "platforms_with_mcp": 1,
        "mcp_servers": 1,
        "skills": 2,
        "engine_subcommands": 1,
        "scripts_with_main": 1,
    }
    md = render_markdown(data)
    assert "trae" in md and "agent-memory-hub" in md and "禁手改" in md


def test_check_passes_after_write_and_fails_on_drift(tmp_path):
    """负样本：**配置一变，产物就必须过期**（否则"实测态"又会变成一张静态快照）。"""
    hub = _hub(tmp_path)
    assert check(hub), "未渲染时应报产物缺失"
    write_products(hub)
    assert check(hub) == []

    # 扰动实测态：新增一个技能目录 → 产物必须失配
    (tmp_path / "skills" / "gamma").mkdir()
    (tmp_path / "skills" / "gamma" / "SKILL.md").write_text("# gamma\n", encoding="utf-8")
    errs = check(hub)
    assert errs and "--write" in errs[0]

    # 重渲后恢复一致
    write_products(hub)
    assert check(hub) == []


def test_check_ignores_generated_at(tmp_path):
    """时间戳必然变，不得参与一致性判定（否则 --check 永远红）。"""
    hub = _hub(tmp_path)
    write_products(hub)
    path = hub / "system" / "capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["generated_at"] = "1999-01-01T00:00:00+08:00"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert check(hub) == []
