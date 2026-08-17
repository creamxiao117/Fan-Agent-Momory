from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.tidy import archive


def _seed_rule(root: Path) -> Path:
    p = root / "rules" / "old-rule.md"
    p.write_text(
        "---\ntype: rule\ntags: [old]\nupdated: 2026-08-01\nstatus: active\nreuse_count: 0\n---\n过时规则。\n",
        encoding="utf-8")
    return p


def test_archive_moves_to_archive_and_marks_archived(tmp_path):
    root = bootstrap(tmp_path)
    src = _seed_rule(root)
    dst = archive(root, "rules/old-rule.md", reason="已被新规则取代")
    assert dst.exists()
    assert not src.exists()
    assert "archived" in dst.read_text(encoding="utf-8")


def test_archive_missing_raises(tmp_path):
    root = bootstrap(tmp_path)
    import pytest
    with pytest.raises(FileNotFoundError):
        archive(root, "rules/nope.md")
