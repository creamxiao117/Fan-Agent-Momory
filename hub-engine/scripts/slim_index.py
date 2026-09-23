# hub-engine/scripts/slim_index.py
"""INDEX 目录化：卡行描述截断 ≤40 字，标题/注释/目录说明行保留。

详情以卡 frontmatter/正文为唯一源（spec S3）；本脚本幂等可重跑。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 卡行：`- 卡名` + 2+ 空格 + 描述。卡名允许点号/中文/加粗包裹（真实 INDEX 形态）。
_CARD = re.compile(r"^(- \S+?)(\s{2,})(.+)$")


def slim_line(line: str, max_desc: int = 40) -> str:
    raw = line.rstrip("\n")
    if raw.startswith("- "):
        # 目录分类说明行（如 `- rules/`）不截断；路径型卡名（libs/x）仍处理
        first = raw[2:].split(None, 1)
        if first and first[0].endswith("/"):
            return line
    m = _CARD.match(raw)
    if not m:
        return line
    name, _sp, desc = m.group(1), m.group(2), m.group(3).strip()
    if len(desc) <= max_desc:
        return line
    cut = desc[:max_desc].rstrip()
    if not cut:
        # max_desc=0（或截断后全空）：退化为纯卡名行，不留分隔符/省略号
        return f"{name}\n" if line.endswith("\n") else name
    return f"{name}    {cut}…\n" if line.endswith("\n") else f"{name}    {cut}…"


def slim_text(text: str, max_desc: int = 40) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("- "):
            out.append(slim_line(line, max_desc=max_desc))
        else:
            out.append(line)
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="INDEX 目录化")
    ap.add_argument("--path", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--max-desc",
        type=int,
        default=40,
        help="卡描述截断上限（API 默认 40；预算紧张时可对真机文件用更小帽）",
    )
    args = ap.parse_args(argv)
    raw = args.path.read_text(encoding="utf-8")
    slim = slim_text(raw, max_desc=args.max_desc)
    if not args.dry_run:
        args.path.write_text(slim, encoding="utf-8")
    print(f"{len(raw)} -> {len(slim)} chars{' (dry-run)' if args.dry_run else ''}")
    if len(slim) > 14_000:
        print("FAIL: 仍 >14000 分项帽")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
