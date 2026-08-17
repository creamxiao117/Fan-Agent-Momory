from pathlib import Path

from common.frontmatter import read_card
from scripts.bootstrap_hub import bootstrap
from tools.tidy import archive


def _seed_rule(root: Path) -> Path:
    p = root / "rules" / "old-rule.md"
    p.write_text(
        "---\ntype: rule\ntags: [old]\nupdated: 2026-08-01\nstatus: active\nreuse_count: 0\n---\n过时规则。\n",
        encoding="utf-8",
    )
    return p


def test_archive_moves_to_archive_and_marks_archived(tmp_path):
    root = bootstrap(tmp_path)
    src = _seed_rule(root)
    dst = archive(root, "rules/old-rule.md", reason="已被新规则取代")
    assert dst.exists()
    assert not src.exists()
    # 保留来源子目录结构：archive/rules/old-rule.md
    assert dst == root / "archive" / "rules" / "old-rule.md"
    card = read_card(dst)
    assert card.status == "archived"
    assert card.extra.get("archived_reason") == "已被新规则取代"
    assert card.body.strip() == "过时规则。"
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "归档 rules/old-rule.md（已被新规则取代）" in log


def test_archive_missing_raises(tmp_path):
    root = bootstrap(tmp_path)
    import pytest

    with pytest.raises(FileNotFoundError):
        archive(root, "rules/nope.md")
