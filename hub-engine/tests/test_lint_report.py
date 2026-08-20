from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from scripts.lint_report import run_report


def test_run_report_writes_file_and_log(tmp_path):
    root = bootstrap(tmp_path)
    path = run_report(root)
    assert path.exists()
    assert "Lint 报告" in path.read_text(encoding="utf-8")
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "首次健康检查完成" in log


def _seed_thin(root: Path) -> None:
    """写入一张正文过短的薄卡，验证软汇报能统计到。"""
    (root / "experience" / "thin.md").write_text(
        "---\ntype: exp\ntags: [x]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n太短\n",
        encoding="utf-8",
    )


def test_run_report_soft_reports_thin_cards(tmp_path):
    root = bootstrap(tmp_path)
    _seed_thin(root)
    path = run_report(root)
    text = path.read_text(encoding="utf-8")
    assert "薄卡体量" in text
    assert "thin.md" in text
