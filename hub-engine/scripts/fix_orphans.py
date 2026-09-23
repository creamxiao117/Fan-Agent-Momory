# @version V2.0 / 2026-09-23 / Hermes + pi / INDEX 未登记卡补登（合并 register_missing_index）
"""INDEX 未登记卡补登器（幂等）。

## 职责（合并后唯一入口）
把「权威区有卡文件、但 INDEX 未登记」的条目补进 INDEX 对应分区。

历史上本仓有**两份**做同一件事的脚本：
- `fix_orphans.py`（V1.0，本文件）——靠 `--list-file`（默认 `tmp/orphan_paths.txt`）喂清单
- `register_missing_index.py`（2026-09-23 我新增）——自动检测 + 用卡自身摘要
两者 SECTION 映射、append 逻辑、幂等策略完全重复。**本 V2.0 合并两者**，
并统一复用公共实现，删除重复者。

## V2.0 变更
1. **可自动检测**：不传 `--list-file` 时，自动扫描权威区找出未登记卡
   （等价于原 `register_missing_index` 的行为，不再需要外部喂清单）
2. **摘要口径统一**：改用 `post_ingest_hook.extract_summary`
   —— 它按卡的写作规范取「一句话结论」并在**子句边界**断句，
   同时修掉了 BOM 敏感性。此前本脚本自带的 `_read_frontmatter_summary`
   只取 H1/首行、不做边界断句、且用 `utf-8` 读（带 BOM 的卡取不到摘要）。
3. **复用公共写入**：改用 `post_ingest_hook.append_to_index`，删掉本地的
   `_append_to_index`（同一逻辑的第二份实现）。
4. **修潜在漏登 bug**：原 `_exists_in_index` 里有 `f"- {slug}" in text` 的
   **子串**匹配 —— slug `foo` 会被 `- foobar` 误判为已登记，从而**静默漏登**。
   现改为按行解析 slug 后精确比对。
5. **默认 dry-run**（原 V1.0 是默认写盘、靠 `--dry-run` 关闭）——
   写 INDEX 属结构变更，默认只报告更安全；加 `--apply` 才写。

## 用法
    python -m scripts.fix_orphans --root <AgentMemoryHub>              # 自动检测，只报告
    python -m scripts.fix_orphans --root <AgentMemoryHub> --apply      # 实际补登
    python -m scripts.fix_orphans --root <AgentMemoryHub> --list-file x.txt --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

from scripts.post_ingest_hook import append_to_index, extract_summary

SECTION_TITLES = {
    "rules": "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "longterm": "## 长期记忆（longterm/）",
    "projects": "## 项目记忆（projects/）",
    "blueprints": "## 技术路径蓝图（blueprints/）",
    "experience": "## 经验（experience/）",
}

AUTHORITY_DIRS = ("rules", "methodology", "longterm", "projects", "blueprints")

# 卡行：`- slug` 或 `- **slug**`，后跟 2+ 空格与描述。
# **slug 字符集不允许 `/`** —— 这是排除目录图例行（`- rules/   权威规则说明`）的关键；
# 口径与 `scripts/audit_index.py` 的 CARD_RE 保持一致（否则两处对"什么算一条登记"判断不一）。
_CARD_LINE = re.compile(r"^- (?:\*\*)?([A-Za-z0-9_\-.\u4e00-\u9fff]+?)(?:\*\*)?\s{2,}")


def registered_slugs(index_path: Path) -> set[str]:
    """INDEX 中已登记的 slug 集合。

    按行解析而非子串匹配——原实现的 `f"- {slug}" in text` 会把 `- foobar`
    误判为已登记 `foo`，造成静默漏登（2026-09-23 修正）。
    """
    text = index_path.read_text(encoding="utf-8-sig", errors="ignore")
    out: set[str] = set()
    for line in text.splitlines():
        m = _CARD_LINE.match(line)
        if m:
            out.add(m.group(1))
    return out


def detect_missing(root: Path, index_path: Path) -> list[Path]:
    """权威区中未登记 INDEX 的卡文件"""
    have = registered_slugs(index_path)
    missing: list[Path] = []
    for d in AUTHORITY_DIRS:
        for p in sorted((root / d).glob("*.md")):
            if p.stem not in have:
                missing.append(p)
    return missing


def _load_list(list_path: Path, root: Path) -> list[Path]:
    return [
        root / line.strip().replace("\\", "/")
        for line in list_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fix-orphans", description="INDEX 未登记卡补登")
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument(
        "--list-file",
        type=Path,
        default=None,
        help="每行一个相对路径；不传则自动检测权威区未登记卡",
    )
    ap.add_argument("--index", type=Path, default=None, help="默认 <root>/INDEX.md")
    ap.add_argument("--max-desc", type=int, default=40)
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = ap.parse_args(argv)

    root = Path(args.root)
    index_path = args.index or root / "INDEX.md"
    if not index_path.exists():
        print(f"INDEX.md 不存在: {index_path}", file=sys.stderr)
        return 2

    if args.list_file:
        if not args.list_file.exists():
            print(f"list file not found: {args.list_file}", file=sys.stderr)
            return 2
        cards = _load_list(args.list_file, root)
    else:
        cards = detect_missing(root, index_path)

    print(
        f"待补登: {len(cards)} 张{'（自动检测）' if not args.list_file else '（来自清单）'}"
    )
    if not cards:
        return 0

    added = skipped = 0
    for card in cards:
        if not card.exists():
            print(f"  [skip] 文件不存在: {card}")
            skipped += 1
            continue
        section = SECTION_TITLES.get(card.parent.name)
        if section is None:
            print(f"  [skip] 无对应分区: {card.name}（目录 {card.parent.name}）")
            skipped += 1
            continue
        summary = extract_summary(card, max_len=args.max_desc)
        if not summary:
            print(f"  [skip] 取不到摘要: {card.name}")
            skipped += 1
            continue
        print(f"  [+] {card.parent.name:12s} {card.stem:52s} → {summary}")
        if args.apply:
            if append_to_index(index_path, section, card.stem, summary):
                added += 1
            else:
                print("      （append_to_index 未写入：分区缺失或已存在）")
                skipped += 1
        else:
            added += 1

    print()
    print(
        f"待补登/已补登: {added}   跳过: {skipped}"
        + ("" if args.apply else "  [dry-run，加 --apply]")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
