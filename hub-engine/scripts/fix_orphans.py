# @version V2.0 / 2026-09-23 / Hermes + pi / INDEX 未登记卡补登（合并 register_missing_index）
"""INDEX 未登记卡补登器（幂等）。

## 职责（合并后唯一入口）
把「权威区有卡文件、但 INDEX 未登记」的条目补进 INDEX 对应分区。

## 边界（2026-09-23 裁定：与 fix_index_registry 保持分开）
本工具只做「**文件有 / INDEX 无**」这一个方向，而且是**纯追加**——
不修改、不删除任何已有条目或文件。
反向问题（「INDEX 有 / 文件无」= 幽灵 slug，需改名/纠偏源文件）由
`fix_index_registry.py` 负责；两者**有意不合并**：后者会动源文件，
危险等级不同，合成一个 CLI 会让 `--apply` 语义变模糊。
与其对应的共享契约在 `scripts/index_consistency.py`（所以分开也不会漂移）。

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
import sys
from pathlib import Path

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

from scripts.index_consistency import (
    AUTHORITY_DIRS,
    SECTION_TITLES,
    registered_slugs,
)
from scripts.post_ingest_hook import append_to_index, extract_summary

# 卡行解析 / 分区表统一在 scripts/index_consistency.py（单一事实源）：
#   此前本文件自带 `SECTION_TITLES`、`fix_index_registry` 另带一套
#   `_CARD_SECTION_TOKENS`，同一契约两份实现必然漂移（2026-09-23 收敛）。


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
