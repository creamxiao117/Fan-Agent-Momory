"""薄卡体检：权威区正文过短卡片 → 候选清单（只读，不自动改卡）"""

from pathlib import Path

# 复用 bootstrap 生成骨架，与 test_lint 同源
from scripts.bootstrap_hub import bootstrap
from scripts.thin_card_scan import scan, to_markdown


def _seed(root: Path) -> None:
    (root / "rules" / "thin.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-19\nstatus: active\nreuse_count: 0\n---\n短。",
        encoding="utf-8",
    )
    (root / "methodology" / "thick.md").write_text(
        "---\ntype: methodology\ntags: [y]\nupdated: 2026-08-19\nstatus: active\nreuse_count: 0\n---\n"
        + "充实正文。" * 40,
        encoding="utf-8",
    )


def test_scan_flags_only_thin(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    thins = scan(root, min_chars=80)
    files = [t["file"] for t in thins]
    assert "thin.md" in files
    assert "thick.md" not in files


def test_scan_sorted_ascending_by_chars(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "rules" / "a.md").write_text(
        "---\ntype: rule\ntags: [a]\nupdated: 2026-08-19\nstatus: active\nreuse_count: 0\n---\n" + "x" * 20,
        encoding="utf-8",
    )
    (root / "rules" / "b.md").write_text(
        "---\ntype: rule\ntags: [b]\nupdated: 2026-08-19\nstatus: active\nreuse_count: 0\n---\n" + "y" * 50,
        encoding="utf-8",
    )
    chars = [t["body_chars"] for t in scan(root, min_chars=80)]
    assert chars == sorted(chars)


def test_scan_skips_archived(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "rules" / "arch.md").write_text(
        "---\ntype: rule\ntags: [a]\nupdated: 2026-08-19\nstatus: archived\nreuse_count: 0\n---\nx",
        encoding="utf-8",
    )
    assert scan(root, min_chars=80) == []


def test_to_markdown_no_thin():
    md = to_markdown([], 80)
    assert "无薄卡" in md