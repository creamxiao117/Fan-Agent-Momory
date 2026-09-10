# @version V1.0 / 2026-09-08 / Hermes / 一次性孤儿补登（修复 L2 报告 34 项 orphan）
"""L2 报告 orphan 补登：把权威区有文件但 INDEX 未登记的卡批量补进 INDEX。

不修改文件、不删除文件——纯追加 INDEX 条目。
复用 post_ingest_hook.py 的 append_to_index 逻辑（行尾前插入）。

支持通过 --list-file 指定多个文件路径（每行一个 rel path）。
"""

import sys
from pathlib import Path as _P

_THIS = _P(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

from pathlib import Path

SECTION_TITLES = {
    "rules": "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "blueprints": "## 技术路径蓝图（blueprints/）",
    "longterm": "## 长期记忆（longterm/）",
    "projects": "## 项目记忆（projects/）",
    "experience": "## 经验（experience/）",
    "notes": "## 经验（experience/）",
}


def _read_frontmatter_summary(card_path: Path) -> str:
    """从 frontmatter tags 或正文首行提取一句话描述。"""
    try:
        text = card_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    lines = text.splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            return s.lstrip("# ").strip()[:200]
    for line in lines:
        s = line.strip()
        if (
            s
            and not s.startswith("#")
            and not s.startswith("---")
            and not s.startswith("type:")
            and not s.startswith("tags:")
        ):
            return s[:200]
    return "(无描述)"


def _exists_in_index(index_path: Path, slug: str) -> bool:
    """幂等：检查 slug 是否已登记（含嵌套 |- 格式和单行多 slug 情况）。"""
    text = index_path.read_text(encoding="utf-8", errors="ignore")
    # 接受 | 后 2+ 空格、- 后 2+ 空格、行内多 slug 等
    return any(
        [
            f"- {slug}    " in text,
            f"- {slug}  " in text,
            f"|- {slug}    " in text,
            f"|- {slug}  " in text,
            # 单行多 slug（罕见）：- slug1  描述-slot slug2  描述
            f"- {slug}" in text,
            f"|- {slug}" in text,
        ]
    )


def _append_to_index(
    index_path: Path, section_title: str, slug: str, summary: str
) -> bool:
    text = index_path.read_text(encoding="utf-8")
    if _exists_in_index(index_path, slug):
        return False
    lines = text.splitlines(keepends=True)
    in_section = False
    section_end_idx = len(lines)
    for i, line in enumerate(lines):
        if line.startswith(section_title):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            section_end_idx = i
            break
    if not in_section:
        return False
    summary_clean = summary.replace("\n", " ").strip()[:250]
    new_line = f"- {slug}    {summary_clean}\n"
    lines.insert(section_end_idx, new_line)
    index_path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="fix-orphans")
    ap.add_argument("--root", required=True)
    ap.add_argument(
        "--list-file",
        default=None,
        help="每行一个相对路径（如 experience/xxx.md）；不传则默认 tmp/orphan_paths.txt",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    default_list = _THIS.parent.parent / "tmp" / "orphan_paths.txt"
    list_path = Path(args.list_file) if args.list_file else default_list

    if not list_path.exists():
        print(f"orphan list file not found: {list_path}", file=sys.stderr)
        return 2

    orphans = [
        line.strip()
        for line in list_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    index_path = root / "INDEX.md"
    if not index_path.exists():
        print(f"INDEX.md 不存在: {index_path}", file=sys.stderr)
        return 2

    added, skipped = [], []
    for rel in orphans:
        rel = rel.replace("\\", "/")
        dir_name = rel.split("/")[0]
        file_name = rel.split("/")[1]
        slug = file_name.removesuffix(".md")
        card_path = root / rel

        if not card_path.exists():
            skipped.append((slug, "file missing"))
            continue

        section_title = SECTION_TITLES.get(dir_name)
        if not section_title:
            skipped.append((slug, f"unknown dir {dir_name}"))
            continue

        if _exists_in_index(index_path, slug):
            skipped.append((slug, "already in INDEX"))
            continue

        summary = _read_frontmatter_summary(card_path)
        if args.dry_run:
            print(f"DRY: would add '{slug}' → {section_title}")
            continue

        if _append_to_index(index_path, section_title, slug, summary):
            added.append(slug)
        else:
            skipped.append((slug, "append returned False"))

    print("== 补登完成 ==")
    print(f"added: {len(added)}")
    if added[:10]:
        print(f"  前10: {added[:10]}")
    print(f"skipped: {len(skipped)}")
    if skipped[:5]:
        print(f"  前5: {skipped[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
