from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.lint import find_index_ghosts, find_orphans, find_schema_drift, lint


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
    assert set(report) == {
        "orphans",
        "ghosts",
        "stale",
        "invalid",
        "schema_drift",
        "notes",
        "hooks",
        "type_dir_mismatch",  # 2026-09-19 补：93590bc 新增 type↔目录一致性维度
    }
    assert isinstance(report["invalid"], int)


def test_lint_ignores_log_and_report_files(tmp_path):
    """retro/log.md 等非卡片文件不应计入无效卡片"""
    root = bootstrap(tmp_path)
    report = lint(root)
    assert report["invalid"] == 0


def _seed_non_authority_drift(root: Path) -> None:
    """非权威区漂移卡：type 非法 + 无 frontmatter（2026-09-11 真实漂移形态）"""
    (root / "experience").mkdir(parents=True, exist_ok=True)
    (root / "experience" / "drift-type.md").write_text(
        "---\ntype: experience\ntags: [x]\nstatus: active\n---\n漂移卡\n",
        encoding="utf-8",
    )
    (root / "experience" / "drift-nofm.md").write_text("# 无 frontmatter\n正文\n", encoding="utf-8")


def test_find_schema_drift_flags_non_authority(tmp_path):
    """非权威区 schema 漂移必须被独立维度检出——权威区 invalid 计数不覆盖它"""
    root = bootstrap(tmp_path)
    _seed_non_authority_drift(root)
    report = lint(root)
    assert report["invalid"] == 0  # 非权威区不计入权威区 invalid
    names = {d["name"] for d in report["schema_drift"]}
    assert names == {"drift-type.md", "drift-nofm.md"}
    errs = {d["name"]: d["errors"] for d in report["schema_drift"]}
    assert any("experience" in e for e in errs["drift-type.md"])
    assert errs["drift-nofm.md"] == ["frontmatter 无法解析"]


def test_schema_drift_clean_hub_is_empty(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    assert find_schema_drift(root) == []
    assert lint(root)["schema_drift"] == []


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
