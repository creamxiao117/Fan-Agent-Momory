# hub-engine/scripts/regen_index_desc.py
"""INDEX 描述重建：用卡自身的摘要（`extract_summary`）替换描述列。

背景（2026-09-23）
------------------
A4「INDEX 目录化」当时用 `slim_index.py --max-desc 10` 做**机械字符截断**，
INDEX 里因此出现大量读不懂的半截词（实测 239/251 条），例如：

    - rules-routing-table    规则与经验路由表（R…
    - gh-star-repo-filter-rule    GitHub 仓库选…

spec S3 要的是「卡名 + ≤40 字**摘要**」，不是把长描述砍 10 个字。本脚本改为：

1. 从卡正文提取摘要（`post_ingest_hook.extract_summary`）——本仓卡的写作规范
   把「一句话结论」放在样板标题之下，该段落即卡自身的摘要，质量与可读性最好；
2. 超长时在**子句边界**（。，、；等）断句，绝不切出半截词；
3. 只改**能解析到卡文件**的条目——目录图例行、笔记行、已归档卡一律保持原样。

幂等可重跑。默认 dry-run，加 `--apply` 写盘。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.post_ingest_hook import extract_summary

# 卡行：`- slug` 或 `- **slug**`，后跟 2+ 空格与描述（与 audit_index 的解析口径一致）
_CARD_LINE = re.compile(r"^- (?:\*\*)?([^\s*]+)(?:\*\*)?(\s{2,})(.+)$")

# 卡片可能所在的目录（相对 hub 根）
CARD_DIRS = (
    "rules",
    "blueprints",
    "methodology",
    "longterm",
    "projects",
    "experience",
    "notes",
)


def _build_card_index(hub: Path) -> dict[str, Path]:
    """slug(stem) → 卡文件路径；同名取第一个（与扫描顺序一致）"""
    index: dict[str, Path] = {}
    for d in CARD_DIRS:
        for p in sorted((hub / d).glob("*.md")):
            index.setdefault(p.stem, p)
    return index


def regen_text(
    text: str, cards: dict[str, Path], max_desc: int
) -> tuple[str, dict[str, list[str]]]:
    """返回 (新文本, 统计)。统计含 rewritten / unchanged / unresolved / empty_summary。"""
    stats: dict[str, list[str]] = {
        "rewritten": [],
        "unchanged": [],
        "unresolved": [],
        "empty_summary": [],
    }
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        m = _CARD_LINE.match(line.rstrip("\n"))
        if not m:
            out.append(line)
            continue
        slug, sep, old_desc = m.group(1), m.group(2), m.group(3).strip()
        card = cards.get(slug)
        if card is None:
            stats["unresolved"].append(slug)
            out.append(line)  # 图例行 / 笔记行 / 已归档卡：原样保留
            continue
        summary = extract_summary(card, max_len=max_desc)
        if not summary:
            stats["empty_summary"].append(slug)
            out.append(line)
            continue
        if summary == old_desc:
            stats["unchanged"].append(slug)
            out.append(line)
            continue
        stats["rewritten"].append(slug)
        newline = (
            f"- {slug}{sep}{summary}\n"
            if line.endswith("\n")
            else f"- {slug}{sep}{summary}"
        )
        out.append(newline)
    return "".join(out), stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="用卡自身摘要重建 INDEX 描述列")
    ap.add_argument("--hub", type=Path, required=True, help="AgentMemoryHub 根")
    ap.add_argument(
        "--index",
        type=Path,
        action="append",
        default=None,
        help="目标 INDEX 文件（可多次；默认根 INDEX.md + INDEX-experience.md）",
    )
    ap.add_argument(
        "--max-desc", type=int, default=40, help="描述上限（默认 40，spec S3）"
    )
    ap.add_argument("--dry-run", action="store_true", help="只报告不写盘（默认行为）")
    ap.add_argument("--apply", action="store_true", help="实际写盘")
    args = ap.parse_args(argv)

    hub = Path(args.hub)
    targets = args.index or [hub / "INDEX.md", hub / "INDEX-experience.md"]
    cards = _build_card_index(hub)
    print(f"卡索引: {len(cards)} 个 slug    描述上限: {args.max_desc}")

    for t in targets:
        if not t.exists():
            print(f"[skip] 不存在: {t}")
            continue
        raw = t.read_text(encoding="utf-8-sig")
        newline = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        new, stats = regen_text(text, cards, args.max_desc)
        print(f"\n{t.name}: {len(text)} -> {len(new)} 字符")
        for k in ("rewritten", "unchanged", "empty_summary", "unresolved"):
            print(f"  {k:14s} {len(stats[k])}")
        if stats["empty_summary"]:
            print(f"    （空摘要前 5：{stats['empty_summary'][:5]}）")
        if args.apply:
            out = new.replace("\n", newline) if newline != "\n" else new
            t.write_text(out, encoding="utf-8", newline="")
            print("  ✅ 已写盘")
        else:
            print("  [dry-run] 未写盘（加 --apply）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
