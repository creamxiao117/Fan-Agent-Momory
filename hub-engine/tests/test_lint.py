from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.lint import find_orphans, lint


def _seed(root: Path) -> None:
    (root / "rules" / "a.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n规则 A\n",
        encoding="utf-8")
    (root / "experience" / "orphan.md").write_text(
        "---\ntype: exp\ntags: [y]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n无人引用的孤立页\n",
        encoding="utf-8")
    (root / "rules" / "stale.md").write_text(
        "---\ntype: rule\ntags: [z]\nupdated: 2026-01-01\nstatus: active\nreuse_count: 0\n---\n半年没更新的陈旧页\n",
        encoding="utf-8")


def test_find_orphans(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    names = [p.name for p in find_orphans(root)]
    assert "orphan.md" in names


def test_lint_reports_stale_pages(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    report = lint(root)
    stale = [i["name"] for i in report["stale"]]
    assert "stale.md" in stale


def test_lint_returns_full_shape(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    report = lint(root)
    assert set(report) == {"orphans", "stale", "invalid", "notes"}
    assert isinstance(report["invalid"], int)
