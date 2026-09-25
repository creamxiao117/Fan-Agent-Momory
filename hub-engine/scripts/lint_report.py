"""跑 Lint 并把报告写入中枢 retro/，同时追加 log 时间线"""

import sys
from pathlib import Path

# 使脚本可从任意 cwd 以脚本方式运行（将 hub-engine/ 加入模块搜索路径）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.frontmatter import today_iso
from scripts.bootstrap_hub import bootstrap
from scripts.thin_card_scan import scan as thin_card_scan
from sync import append_log
from tools.lint import lint


def _thin_section(root: Path) -> str:
    """薄卡体量软汇报：只读统计，接每日巡检日志而不并入 lint 判定（避免误告警噪音）。"""
    try:
        thins = thin_card_scan(root)
    except (OSError, ValueError):
        return "- 薄卡体量（<80 字）: 统计失败（跳过）\n"
    if not thins:
        return "- 薄卡体量（<80 字）: 0（无薄卡）\n"
    lines = [
        f"- 薄卡体量（<80 字）: {len(thins)} 张（仅信息，不算告警；纵列前 3）",
        "  | 体量 | 类型目录 | 文件 |",
        "  | --- | --- | --- |",
    ]
    for t in thins[:3]:
        lines.append(f"  | {t['body_chars']} | {t['dir']} | `{t['file']}` |")
    lines.append("  （完整清单见 thin_card_scan.py --json；人工决定补正文或归档）")
    return "\n".join(lines) + "\n"


def run_report(root: str | Path) -> Path:
    root = Path(root)
    bootstrap(root)
    report = lint(root)
    path = root / "retro" / f"lint-report-{today_iso()}.md"
    path.write_text(
        f"""# Lint 报告 {today_iso()}

- 孤儿页: {report["orphans"]}
- 陈旧页: {report["stale"]}
- 无效卡片: {report["invalid"]}
- 备注: {report["notes"]}
{_thin_section(root)}""",
        encoding="utf-8",
    )
    append_log(root, "lint", "首次健康检查完成")
    return path


if __name__ == "__main__":
    # 2026-09-25（审计 P2-a）：改用 argparse。
    # 旧实现是 `sys.argv[1] if len(sys.argv) > 1 else "AgentMemoryHub"` —— 传 `--root X`
    # 会把字面量 `--root` 当成路径，在 CWD 下真的建出一棵名为 `--root` 的中枢骨架（实测复现）。
    import argparse

    ap = argparse.ArgumentParser(description="生成中枢 lint 报告（retro/lint-report-<date>.md）")
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "AgentMemoryHub",
        help="中枢根目录（默认：本仓 AgentMemoryHub）",
    )
    ap.add_argument(
        "positional_root",
        nargs="?",
        type=Path,
        default=None,
        help="兼容旧用法：直接给位置参数当根目录（等价 --root）",
    )
    args = ap.parse_args()
    root = args.positional_root or args.root
    if str(root).startswith("--"):  # 防再次把参数名当路径
        ap.error(f"根目录看起来是参数名：{root}")
    print(f"报告已写入: {run_report(root)}")
