"""Lint：周期性库健康检查（孤儿页 / 陈旧页 / 无效卡片 / 摘要）"""

from datetime import date
from pathlib import Path

from common.frontmatter import today_date, try_read_card, validate_card

AUTHORITY_DIRS = ("rules", "experience", "projects", "libs", "retro")
STALE_DAYS = 180


def _all_cards(root: Path) -> list:
    """返回 (dir, Path, Card) 列表；跳过时间线/报告等非卡片文件"""
    out = []
    for sub in AUTHORITY_DIRS:
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            # 时间线/报告文件无 frontmatter，非卡片，不计入健康检查
            if p.name == "log.md" or p.name.startswith("lint-report-"):
                continue
            out.append((sub, p, try_read_card(p)))
    return out


def find_orphans(root: Path) -> list[Path]:
    """无入链指向的页面（INDEX.md 不计入引用）"""
    root = Path(root)
    index_text = ""
    if (root / "INDEX.md").exists():
        index_text = (root / "INDEX.md").read_text(encoding="utf-8")
    orphans = []
    for sub, p, card in _all_cards(root):
        if card is None or card.status == "archived":
            continue
        stem = p.stem
        referenced = stem in index_text
        if not referenced:
            # 粗略排除"自身目录内被其他文件引用"的情况
            for sub2, p2, card2 in _all_cards(root):
                if p2 != p and stem in p2.read_text(encoding="utf-8"):
                    referenced = True
                    break
        if not referenced:
            orphans.append(p)
    return orphans


def lint(root: Path) -> dict:
    """健康检查报告：orphans / stale / invalid / notes"""
    root = Path(root)
    stale, invalid = [], 0  # invalid 是 int 计数（计划原文有 bug）
    for sub, p, card in _all_cards(root):
        if card is None:
            invalid += 1
            continue
        errs = validate_card(card)
        if errs:
            invalid += 1
            continue
        try:
            age = (today_date() - date.fromisoformat(card.updated)).days
        except ValueError:
            stale.append({"name": p.name, "dir": sub, "updated": card.updated})
            continue
        if age > STALE_DAYS and card.status == "active":
            stale.append({"name": p.name, "dir": sub, "updated": card.updated})
    total = sum(1 for _ in _all_cards(root))
    return {
        "orphans": [str(p) for p in find_orphans(root)],
        "stale": stale,
        "invalid": invalid,
        "notes": f"共检查 {total} 张卡片",
    }
