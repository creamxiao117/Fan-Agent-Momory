# hub-engine/scripts/register_missing_index.py
"""把权威区中「未登记 INDEX」的卡补登记（幂等）。

背景（2026-09-23）
------------------
`audit` 的 orphan 维度反复报 10 项 `[high] 权威区有 X 但 INDEX 未登记`，
其中包含 **`rules/global-rules.md`**——而 `rules-routing-table` 的 GR-1~4 正是
指向它。也就是说：路由表让 Agent 去读 `global-rules.md`，但 INDEX 里查不到它。

成因：卡级合并/拆分（内容并入 X、拆分核心+附录）只改了卡文件，**没有同步登记
新卡到 INDEX**，于是新目标卡长期缺席。

本文补登记，并可作为后续同类缺口的修复入口。默认 dry-run。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.post_ingest_hook import append_to_index, extract_summary

# 目录 → INDEX 分区标题（必须与 INDEX.md 内的实际标题一致）
DIR2SECTION = {
    "rules": "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "longterm": "## 长期记忆（longterm/）",
    "projects": "## 项目记忆（projects/）",
    "blueprints": "## 技术路径蓝图（blueprints/）",
}

AUTHORITY_DIRS = ("rules", "methodology", "longterm", "projects", "blueprints")


def _registered_slugs(index_path: Path) -> set[str]:
    """INDEX 中已出现的 slug（用与 audit 相同的宽松口径：出现 `- <slug>` 即可）"""
    import re

    text = index_path.read_text(encoding="utf-8-sig")
    out: set[str] = set()
    for m in re.finditer(r"^- (?:\*\*)?([^\s*]+)", text, re.MULTILINE):
        out.add(m.group(1).rstrip("/"))
    return out


def find_missing(hub: Path, index_path: Path) -> list[Path]:
    """权威区中未登记 INDEX 的卡文件"""
    registered = _registered_slugs(index_path)
    missing = []
    for d in AUTHORITY_DIRS:
        for p in sorted((hub / d).glob("*.md")):
            if p.stem not in registered:
                missing.append(p)
    return missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="补登记权威区未入 INDEX 的卡")
    ap.add_argument("--hub", type=Path, required=True)
    ap.add_argument("--index", type=Path, default=None, help="默认 <hub>/INDEX.md")
    ap.add_argument("--max-desc", type=int, default=40)
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = ap.parse_args(argv)

    hub = Path(args.hub)
    index_path = args.index or hub / "INDEX.md"
    missing = find_missing(hub, index_path)
    print(f"未登记卡: {len(missing)}")
    if not missing:
        return 0

    added = skipped = 0
    for p in missing:
        section = DIR2SECTION.get(p.parent.name)
        if section is None:
            print(f"  [skip] 无对应分区: {p.relative_to(hub)}")
            skipped += 1
            continue
        summary = extract_summary(p, max_len=args.max_desc)
        if not summary:
            print(f"  [skip] 取不到摘要: {p.relative_to(hub)}")
            skipped += 1
            continue
        print(f"  [+] {section[3:]:14s} {p.stem:52s} → {summary}")
        if args.apply:
            if append_to_index(index_path, section, p.stem, summary):
                added += 1
            else:
                print("      （append_to_index 未写入：分区缺失或已存在）")
                skipped += 1
        else:
            added += 1

    print()
    print(
        f"待登记/已登记: {added}   跳过: {skipped}"
        + ("" if args.apply else "  [dry-run]")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
