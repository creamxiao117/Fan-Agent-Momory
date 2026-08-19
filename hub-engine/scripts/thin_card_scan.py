"""薄卡体检：扫描权威区正文过短的卡片，提示补信息（一次性轻量,不引入指标/健康分）。

背景：A-lite 完整立项对单仓 83 卡是过度工程（成熟度单峰 active、语言合规易误告警），
仅"体量不足"一维值得留——此脚本即该维的轻量化落地，只读输出候选清单，不自动改卡。

判定：卡片 frontmatter 之后的正文字符数（去首尾空白）低于 `--min-chars` 即视为薄卡；
默认只列体量升序清单，供人工决定补正文还是归档。刻意**不**并入 lint，避免对短清单类
卡片（如规则名即要点、指针卡）制造误告警噪音。

用法：
  python hub-engine/scripts/thin_card_scan.py --root AgentMemoryHub                      # 终端 Markdown
  python hub-engine/scripts/thin_card_scan.py --root AgentMemoryHub --json               # 结构化到 stdout
  python hub-engine/scripts/thin_card_scan.py --root AgentMemoryHub --min-chars 120 -o work/thin.md
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 保证可 import tools.*

from tools.lint import _all_cards

MIN_CHARS_DEFAULT = 80


def scan(root: Path, min_chars: int = MIN_CHARS_DEFAULT) -> list[dict]:
    """返回体量升序的薄卡清单；每项 {rel_path, dir, file, body_chars, line_count}。"""
    root = Path(root)
    out: list[dict] = []
    for sub, p, card in _all_cards(root):
        if card is None or card.status == "archived":
            continue
        body = card.body.strip()
        body_chars = len(body)
        if body_chars < min_chars:
            out.append(
                {
                    "rel_path": p.relative_to(root).as_posix(),
                    "dir": sub,
                    "file": p.name,
                    "body_chars": body_chars,
                    "line_count": len(body.splitlines()),
                }
            )
    out.sort(key=lambda x: x["body_chars"])
    return out


def to_markdown(thins: list[dict], min_chars: int) -> str:
    lines = [
        "# 薄卡体检清单",
        "",
        f"- 判定：正文（frontmatter 后）少于 {min_chars} 字",
        f"- 命中：{len(thins)} 张",
        "",
    ]
    if thins:
        lines += ["| 体量(字) | 类型目录 | 文件 |", "| --- | --- | --- |"]
        for t in thins:
            lines.append(f"| {t['body_chars']} | {t['dir']} | `{t['file']}` |")
        lines += ["", "（人工决定补正文或归档）"]
    else:
        lines.append("（无薄卡）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="thin-card-scan", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT, help="正文最低字符数阈值")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON 到 stdout")
    ap.add_argument("-o", "--output", default=None, help="写入 Markdown 文件路径")
    args = ap.parse_args(argv)
    thins = scan(Path(args.root), args.min_chars)
    if args.json:
        print(json.dumps(thins, ensure_ascii=False, indent=2))
        return 0
    md = to_markdown(thins, args.min_chars)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"薄卡清单已写入：{args.output}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())