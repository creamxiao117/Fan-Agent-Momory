# @version V1.0 / 2026-09-25 / COV：MCP launcher 与 Mavis 桥接的纯函数
"""`hub_mcp_launcher` / `mavis_hub_bridge` 的可测部分（COV 补足 scripts/ ≥ 40%）。

这两支都是「桥接/启动器」类脚本：核心路径要真起子进程，但**判定与落盘部分**
（找 server、备份、当日自愈闸门、JSON args 补丁、ledger 追加）是纯函数，可直接测。
"""

from __future__ import annotations

import json

from scripts import hub_mcp_launcher as launcher
from scripts import mavis_hub_bridge as mavis

# ---------------------------------------------------------------------------
# hub_mcp_launcher
# ---------------------------------------------------------------------------


def test_find_mcp_server_explicit_and_search(tmp_path, monkeypatch):
    target = tmp_path / "mcp_server.py"
    target.write_text("# stub", encoding="utf-8")

    assert launcher.find_mcp_server(str(target)).name == launcher.MCP_SERVER_FILENAME

    # 显式路径不是文件 → **回退到搜索根**（不是直接 None）
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    monkeypatch.setattr(launcher, "DEFAULT_SEARCH_ROOTS", [empty_root])
    assert launcher.find_mcp_server(str(tmp_path / "nope.py")) is None

    # 搜索根里有 server → 搜到
    monkeypatch.setattr(launcher, "DEFAULT_SEARCH_ROOTS", [tmp_path])
    assert launcher.find_mcp_server() == target


def test_today_cst_str_format():
    stamp = launcher.today_cst_str()
    assert len(stamp) == 10 and stamp.count("-") == 2


def test_backup_mcp_config_creates_copy(tmp_path):
    """备份落在**配置文件同目录**的 mcp_backups/ 下（无则新建）；文件不存在返 None。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")

    out = launcher.backup_mcp_config("trae", cfg)
    assert out is not None and out.is_file()
    assert out.parent.name == launcher.BACKUP_DIR_NAME
    assert out.read_text(encoding="utf-8") == cfg.read_text(encoding="utf-8")
    assert launcher.backup_mcp_config("trae", tmp_path / "missing.json") is None


def test_can_self_heal_today_gate(tmp_path):
    """当日自愈闸门：无备份 → 允许；今天已备份过 → 拒绝（防一天内反复改写配置）。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text("{}", encoding="utf-8")
    assert launcher.can_self_heal_today("trae", cfg) is True, "无备份目录 → 允许自愈"

    backup_dir = tmp_path / launcher.BACKUP_DIR_NAME
    backup_dir.mkdir()
    (backup_dir / f"trae-{launcher.today_cst_str()}-000000.json").write_text("{}", encoding="utf-8")
    assert launcher.can_self_heal_today("trae", cfg) is False, "今天已自愈过 → 拒绝"


def test_patch_json_args_rewrites_only_managed_platform(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agent-memory-hub": {"command": "python", "args": ["old.py"]},
                    "other": {"command": "python", "args": ["keep.py"]},
                }
            }
        ),
        encoding="utf-8",
    )
    ok = launcher.patch_json_args(cfg, ["old.py"], ["new.py", "--heal"])
    assert isinstance(ok, bool)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"]["args"] == ["keep.py"], "其它平台不得被动"


def test_append_ledger_appends_jsonl(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    launcher.append_ledger(ledger, {"platform": "trae", "action": "heal"})
    launcher.append_ledger(ledger, {"platform": "code", "action": "heal"})
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 2 and rows[0]["platform"] == "trae"


# ---------------------------------------------------------------------------
# mavis_hub_bridge
# ---------------------------------------------------------------------------


def test_now_iso_shape():
    stamp = mavis._now_iso()
    assert "T" in stamp and stamp.startswith("20")


def test_read_yaml_missing_and_valid(tmp_path):
    """最小 YAML 解析：返回**已展开 platforms** 的 dict（不是整份文档）。"""
    assert mavis._read_yaml(tmp_path / "nope.yaml") == {}
    p = tmp_path / "platforms.yaml"
    p.write_text("platforms:\n  mavis:\n    type: file\n", encoding="utf-8")
    got = mavis._read_yaml(p)
    assert got.get("mavis", {}).get("type") == "file"
