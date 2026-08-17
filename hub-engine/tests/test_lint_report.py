from scripts.bootstrap_hub import bootstrap
from scripts.lint_report import run_report


def test_run_report_writes_file_and_log(tmp_path):
    root = bootstrap(tmp_path)
    path = run_report(root)
    assert path.exists()
    assert "Lint 报告" in path.read_text(encoding="utf-8")
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "首次健康检查完成" in log
