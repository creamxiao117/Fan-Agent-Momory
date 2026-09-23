# @version V1.0 / 2026-09-11 / Hermes / INDEX 登记一致性修复器（幽灵 slug 自动纠偏）
"""INDEX.md 登记一致性修复器（幂等，默认 dry-run）。

背景（2026-09-11 实测）：
    手动登记的 INDEX 行不总等于卡片文件名 stem，导致 audit_index 同时报
    「幽灵登记」（slug 无文件）与「未登记」（文件无 slug）。典型成因是登记时
    用了卡片的 frontmatter title/缩写，而非文件名。

本脚本只自动做**确定无歧义**的一件事：
    幽灵 slug → 唯一候选文件的 stem（候选来源：① frontmatter title 完全相等
    ② 文件名 = <日期>-<slug> 形式）。候选不唯一 / 候选 stem 已被登记 / 无候选
    一律只报告，不猜。

其余三类只报告（补描述属内容决策，交人工）：
    - 裸行 `- slug`（缺描述 → audit 解析不到，会被当成未登记）
    - 权威区文件未登记
    - 疑似散文行被当成登记行

用法：
  python scripts/fix_index_registry.py --root ..\\AgentMemoryHub
  python scripts/fix_index_registry.py --root ..\\AgentMemoryHub --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.frontmatter import card_title
from scripts.audit_index import (
    _ALL_SCAN_DIRS,
    AUTHORITY_DIRS,
    _authority_files,
    _parse_index,
)
from scripts.index_consistency import is_card_section

# 分区判定 / 标题 / 摘要统一到共享位置（2026-09-23）：
#   本文件原自带 `_CARD_SECTION_TOKENS` + `_is_card_section`（第二套分区机制）、
#   与 `_card_title`（取卡标题的私有副本）。同一契约多份实现必然漂移，已收敛：
#     - 分区判定 → scripts/index_consistency.is_card_section
#               （token 由 SECTION_TITLES 派生，不再手写第二份列表）
#     - 卡标题   → common.frontmatter.card_title（frontmatter title → H1）
#
#  注：**不要**把卡标题换成 post_ingest_hook.extract_summary——两者用途不同：
#      card_title 取“身份”（用于幽灵 slug 匹配），extract_summary 取“摘要内容”
#      （跳过样板标题读正文，结果往往不等于标题）。换错会让幽灵纠偏失效。


_CRLF = "\r\n"


def _candidates(ghost: str, files: dict[str, Path], root: Path) -> list[str]:
    """幽灵 slug 的候选文件名 stem（唯一才可用）。

    注意 rel 是相对路径，读文件必须拼回 root，否则取不到标题（实测踩坑）。
    标题统一用 common.frontmatter.card_title（原 _card_title 是其私有副本，已上提）。
    """
    hits = []
    for slug, rel in files.items():
        if slug.endswith("-" + ghost):
            hits.append(slug)
            continue
        title = card_title(root / rel)
        if title and title == ghost:
            hits.append(slug)
    return sorted(set(hits))


def scan(root: Path) -> dict:
    """扫描并返回四类问题（不改盘）"""
    root = Path(root)
    index_path = root / "INDEX.md"
    by_slug, entries = _parse_index(index_path)
    files = _authority_files(root, _ALL_SCAN_DIRS)

    # 裸行：形如 `- slug`（无描述）→ INDEX_ENTRY_RE 解析不到，会被 audit 当成「未登记」。
    # 仅在「卡片清单分区」内判定，并排除散文/加粗行：否则 `- 使用约定…`、`- **提示** …`
    # 会被误报（2026-09-11 实测 3 处误报）。
    raw_lines = index_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    section = ""
    bare = []
    for i, ln in enumerate(raw_lines, start=1):
        if ln.startswith("## "):
            section = ln
            continue
        if not is_card_section(section) or not ln.startswith("- ") or "  " in ln:
            continue
        token = ln[2:].strip()
        if token.startswith("*") or "：" in token or "。" in token:
            continue
        bare.append((i, token))

    ghost_fixable, ghost_manual = [], []
    for entry in entries:
        slug = entry["slug"]
        if slug in files:
            continue
        cands = _candidates(slug, files, root)
        # 候选 stem 已被登记 → 这行其实是重复登记，不能改（改名会变两条同 slug）
        cands = [c for c in cands if c not in by_slug]
        if len(cands) == 1:
            ghost_fixable.append((entry["line_no"], slug, cands[0]))
        else:
            ghost_manual.append((entry["line_no"], slug, cands))

    unregistered = [
        (rel.parts[0], rel.name)
        for slug, rel in sorted(_files_sorted(files).items())
        if slug not in by_slug
    ]
    return {
        "ghost_fixable": ghost_fixable,
        "ghost_manual": ghost_manual,
        "bare": bare,
        "unregistered": unregistered,
        "entries": len(entries),
        "files": len(files),
    }


def _files_sorted(files: dict[str, Path]) -> dict[str, Path]:
    """只保留权威区文件（非权威区不参与 orphan 判定，仅登记）"""
    return {s: p for s, p in files.items() if p.parts[0] in AUTHORITY_DIRS}


def apply_ghost_fixes(root: Path, fixes: list[tuple[int, str, str]]) -> int:
    """按行号改写幽灵 slug → 候选 stem（保留原 EOL）"""
    index_path = root / "INDEX.md"
    with open(index_path, encoding="utf-8", newline="") as fh:
        lines = fh.read().split(_CRLF)
    done = 0
    for line_no, old, new in fixes:
        i = line_no - 1
        if 0 <= i < len(lines) and lines[i].startswith(f"- {old}"):
            lines[i] = lines[i].replace(f"- {old}", f"- {new}", 1)
            done += 1
    if done:
        with open(index_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(_CRLF.join(lines))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(prog="fix-index-registry", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--apply", action="store_true", help="真正写盘（缺省 dry-run）")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    res = scan(root)
    print(
        f"[fix_index_registry] 登记 {res['entries']} 条 / 文件 {res['files']} 张 / "
        f"幽灵可自动纠偏 {len(res['ghost_fixable'])} / 幽灵需人工 {len(res['ghost_manual'])} / "
        f"裸行 {len(res['bare'])} / 未登记 {len(res['unregistered'])}"
    )
    for line_no, old, new in res["ghost_fixable"]:
        print(f"  🔧 L{line_no}: '{old}' → '{new}'（候选唯一）")
    for line_no, slug, cands in res["ghost_manual"]:
        print(f"  ⚠️ L{line_no}: '{slug}' 无文件；候选={cands or '无'}")
    for line_no, slug in res["bare"]:
        print(f"  ⚠️ L{line_no}: 裸行 '{slug}' 缺描述（audit 解析不到，会被当成未登记）")
    for d, name in res["unregistered"]:
        print(f"  ⚠️ {d}/{name} 未登记 INDEX")

    if args.apply and res["ghost_fixable"]:
        done = apply_ghost_fixes(root, res["ghost_fixable"])
        print(f"[fix_index_registry] [APPLIED] 改写 {done} 行幽灵 slug")
    elif not args.apply:
        print("[fix_index_registry] [DRY-RUN] 未写盘（加 --apply 执行幽灵 slug 纠偏）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
