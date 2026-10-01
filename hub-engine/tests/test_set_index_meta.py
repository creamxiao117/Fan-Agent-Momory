"""T1/状态回写入口 + 卡字段安全写法的单测。

背景：枚举迁出 L0 后，INDEX 是**渲染产物**，Agent 不能再手改索引行（会被
commit 钩子 exit 6 打红）。回写必须走「写卡 frontmatter → 重渲染」这条路。
"""

from pathlib import Path

import pytest
import yaml

from scripts.card_fields import remove_field, set_fields, yaml_line
from scripts.render_index import L0_NAME, check
from scripts.set_index_meta import find_card, main

CARD = """---
type: rule
tags: [demo]
updated: '2026-10-01'
status: active
---

演示描述一句话。
"""


def _hub(tmp_path: Path) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    (hub / "rules").mkdir(parents=True)
    (hub / "rules" / "demo-rule.md").write_text(CARD, encoding="utf-8")
    return hub


def test_yaml_line_roundtrips_tricky_values():
    """中文冒号/引号/井号都不能把 YAML 写坏（手拼必踩）"""
    for value in ("（T1 09-30 ✅ 3/3，reuse 1）", "说「假绿」：不是 'fake'", "# 井号开头", "a: b"):
        assert yaml.safe_load(yaml_line("index_note", value))["index_note"] == value


def test_set_fields_appends_and_replaces(tmp_path: Path):
    hub = _hub(tmp_path)
    p = hub / "rules" / "demo-rule.md"

    set_fields(p, {"index_note": "（T1 ✅）"})
    assert "index_note: （T1 ✅）" in p.read_text(encoding="utf-8")

    set_fields(p, {"index_note": "（T1 09-30 ✅）"})
    text = p.read_text(encoding="utf-8")
    assert text.count("index_note:") == 1, "原地替换，不得重复添加"
    assert "09-30" in text


def test_set_fields_preserves_bom_and_crlf(tmp_path: Path):
    p = tmp_path / "bom.md"
    p.write_bytes("\ufeff---\r\ntype: rule\r\n---\r\n\r\n正文\r\n".encode())

    set_fields(p, {"index_note": "（T1 ✅）"})

    raw = p.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", "BOM 必须保留"
    assert b"index_note" in raw
    assert raw.count(b"\r\n") >= 4, "换行风格必须保留（默认 write_text 会翻成 \\r\\n 全文件漂移）"


def test_remove_field(tmp_path: Path):
    p = tmp_path / "c.md"
    p.write_text("---\ntype: rule\nindex_note: x\n---\n\n正文\n", encoding="utf-8")

    assert remove_field(p, "index_note") is True
    assert "index_note" not in p.read_text(encoding="utf-8")
    assert remove_field(p, "index_note") is False


def test_find_card_across_dirs(tmp_path: Path):
    hub = _hub(tmp_path)
    (hub / "blueprints").mkdir()
    (hub / "blueprints" / "bp.md").write_text(CARD, encoding="utf-8")

    assert find_card(hub, "demo-rule").name == "demo-rule.md"
    assert find_card(hub, "bp").parent.name == "blueprints"
    assert find_card(hub, "nope") is None


def test_cli_writes_note_and_rerenders(tmp_path: Path, capsys):
    hub = _hub(tmp_path)

    assert main(["--root", str(hub), "--slug", "demo-rule", "--note", "（T1 09-30 ✅）"]) == 0

    assert check(hub) == [], "写卡后必须同步重渲染（否则 --check 立刻红）"
    assert "（T1 09-30 ✅）" in (hub / "INDEX-full.md").read_text(encoding="utf-8")
    capsys.readouterr()


def test_cli_dry_run_does_not_write(tmp_path: Path, capsys):
    hub = _hub(tmp_path)
    before = (hub / "rules" / "demo-rule.md").read_text(encoding="utf-8")

    assert main(["--root", str(hub), "--slug", "demo-rule", "--note", "x", "--dry-run"]) == 0

    assert (hub / "rules" / "demo-rule.md").read_text(encoding="utf-8") == before
    capsys.readouterr()


def test_cli_unknown_slug_returns_2(tmp_path: Path, capsys):
    assert main(["--root", str(_hub(tmp_path)), "--slug", "nope", "--note", "x"]) == 2
    capsys.readouterr()


def test_cli_requires_action(tmp_path: Path, capsys):
    assert main(["--root", str(_hub(tmp_path)), "--slug", "demo-rule"]) == 4
    capsys.readouterr()


def test_cli_clear_note(tmp_path: Path, capsys):
    hub = _hub(tmp_path)
    main(["--root", str(hub), "--slug", "demo-rule", "--note", "（T1 ✅）"])
    assert main(["--root", str(hub), "--slug", "demo-rule", "--clear-note"]) == 0

    assert "index_note" not in (hub / "rules" / "demo-rule.md").read_text(encoding="utf-8")
    assert check(hub) == []
    capsys.readouterr()


def test_l0_still_has_no_card_lines_after_write(tmp_path: Path, capsys):
    """回写**绝不能**把枚举写回 L0（这正是形状门禁防的那件事）"""
    from scripts.startup_budget import check_l0_shape

    hub = _hub(tmp_path)
    main(["--root", str(hub), "--slug", "demo-rule", "--note", "（T1 ✅）"])

    assert check_l0_shape((hub / L0_NAME).read_text(encoding="utf-8")) == []
    capsys.readouterr()


@pytest.mark.parametrize("flag", ["--note", "--desc"])
def test_cli_partial_fields(flag, tmp_path: Path, capsys):
    hub = _hub(tmp_path)
    assert main(["--root", str(hub), "--slug", "demo-rule", flag, "值"]) == 0
    assert check(hub) == []
    capsys.readouterr()
