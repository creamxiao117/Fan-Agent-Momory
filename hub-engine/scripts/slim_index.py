# hub-engine/scripts/slim_index.py
"""INDEX 目录化：卡行描述裁到 ≤max_desc 字符，标题/注释/目录说明行保留。

详情以卡 frontmatter/正文为唯一源（spec S3）；本脚本幂等可重跑。

2026-09-23 变更：改用**子句边界断句**（。，、；等），不再 `desc[:N]` 硬切。
旧行为会切出读不懂的半截词（实测 `--max-desc 10` 下 239/251 条变成
「GitHub 仓库选…」），虽省字符但丢了信息。

注意：本脚本只做「截短」；需要**提升可读性**应改用
`scripts/regen_index_desc.py`（用卡自身摘要重建描述列）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.post_ingest_hook import cut_at_boundary

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
    # 子句边界断句（无边界时退到空格/硬切，由 cut_at_boundary 兜底）
    cut = cut_at_boundary(desc, max_desc)
    if not cut:
        # max_desc=0（或截断后全空）：退化为纯卡名行，不留分隔符/省略号
        return f"{name}\n" if line.endswith("\n") else name
    return f"{name}{_sp}{cut}\n" if line.endswith("\n") else f"{name}{_sp}{cut}"


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
