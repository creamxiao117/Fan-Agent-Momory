from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.lint import find_index_ghosts, find_orphans, lint


def _seed(root: Path) -> None:
    (root / "rules" / "a.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n规则 A\n",
        encoding="utf-8",
    )
    # 2026-09-02 权威区收缩：孤儿检测只扫 5 权威区，孤立页须落在 rules 下
    (root / "rules" / "orphan.md").write_text(
        "---\ntype: rule\ntags: [y]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n无人引用的孤立页\n",
        encoding="utf-8",
    )
    (root / "rules" / "stale.md").write_text(
        "---\ntype: rule\ntags: [z]\nupdated: 2026-01-01\nstatus: active\nreuse_count: 0\n---\n半年没更新的陈旧页\n",
        encoding="utf-8",
    )


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
    assert set(report) == {"orphans", "ghosts", "stale", "invalid", "notes", "hooks"}
    assert isinstance(report["invalid"], int)


def test_lint_ignores_log_and_report_files(tmp_path):
    """retro/log.md 等非卡片文件不应计入无效卡片"""
    root = bootstrap(tmp_path)
    report = lint(root)
    assert report["invalid"] == 0


def test_find_index_ghosts_reports_missing(tmp_path):
    """幽灵登记：INDEX 登记了卡名但权威区无对应文件 → 应被检出。"""
    root = bootstrap(tmp_path)
    (root / "INDEX.md").write_text("- missing-card 幽灵登记\n", encoding="utf-8")
    ghosts = find_index_ghosts(root)
    assert "missing-card" in ghosts


def test_lint_reports_ghosts(tmp_path):
    root = bootstrap(tmp_path)
    (root / "INDEX.md").write_text("- phantom 幽灵登记\n", encoding="utf-8")
    report = lint(root)
    assert "phantom" in report["ghosts"]
