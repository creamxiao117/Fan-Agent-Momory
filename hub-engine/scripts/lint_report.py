"""跑 Lint 并把报告写入中枢 retro/，同时追加 log 时间线"""
from datetime import date
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from sync import append_log
from tools.lint import lint


def run_report(root: str | Path) -> Path:
    root = Path(root)
    bootstrap(root)
    report = lint(root)
    path = root / "retro" / f"lint-report-{date.today().isoformat()}.md"
    path.write_text(f"""# Lint 报告 {date.today().isoformat()}

- 孤儿页: {report['orphans']}
- 陈旧页: {report['stale']}
- 无效卡片: {report['invalid']}
- 备注: {report['notes']}
""", encoding="utf-8")
    append_log(root, "lint", "首次健康检查完成")
    return path


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\AIwork\AgentMemoryHub"
    print(f"报告已写入: {run_report(target)}")
