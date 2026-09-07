"""Lint：周期性库健康检查（孤儿页 / 陈旧页 / 无效卡片 / 摘要）"""

import re
from datetime import date
from pathlib import Path

from common.frontmatter import today_date, try_read_card, validate_card

# 仅 5 个权威区目录
AUTHORITY_DIRS = (
    "rules",
    "blueprints",
    "methodology",
    "longterm",
    "projects",
)
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


# INDEX 合法登记目标：非权威区目录（experience/notes 保留可检索/可登记，
# 只是不参与去重/向量/检索主流程；指向它们的登记不是幽灵）。2026-09-02 口径定稿。
_NON_AUTH_INDEX_DIRS = ("experience", "notes")


def find_index_ghosts(root: Path) -> list[str]:
    """反向盲区：INDEX.md 已登记、但磁盘查无对应卡文件的『幽灵登记』。

    与 find_orphans 双向互补：
    - 孤儿 = 文件在、但 INDEX/他卡无引用（有人评）→ 现有逻辑覆盖；
    - 幽灵 = INDEX 登记了、但卡文件缺失/改名 → 本函数兜底。
    复现 ingest 不会自动更新 INDEX 而造成的『登记漂移』。

    注意：existing 集合 = 权威区 5 目录 + 非权威区(experience/notes)文件；
    否则 2026-09-02 权威区收缩后，73 张 experience 历史登记会被误判幽灵。
    """
    root = Path(root)
    index_path = root / "INDEX.md"
    if not index_path.exists():
        return []
    index_text = index_path.read_text(encoding="utf-8")
    ghosts = []
    existing = {p.stem for sub, p, card in _all_cards(root)}
    for sub in _NON_AUTH_INDEX_DIRS:
        d = root / sub
        if d.exists():
            existing |= {p.stem for p in d.glob("*.md")}
    for line in index_text.splitlines():
        line = line.strip()
        if not line.startswith(("- ", "* ")):
            continue
        # 登记行形如 `- 卡名 描述...`，取首列词作为登记名
        stem = line[2:].strip().split()[0].rstrip(":").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", stem) or "/" in stem:
            continue
        if stem not in existing:
            ghosts.append(stem)
    return ghosts


def find_orphans(root: Path) -> list[Path]:
    """无入链指向的页面（INDEX.md 不计入引用）"""
    root = Path(root)
    index_text = ""
    if (root / "INDEX.md").exists():
        index_text = (root / "INDEX.md").read_text(encoding="utf-8")
    orphans = []
    for sub, p, card in _all_cards(root):
        if card is None or card.status in ("archived", "reference"):
            continue
        # 缺失 status 视为 active（待补全），不触发 orphan 告警
        if card.status is None:
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
        "ghosts": find_index_ghosts(root),
        "hooks": [],  # 预留：hook 漂移检测（未实现）
        "stale": stale,
        "invalid": invalid,
        "notes": f"共检查 {total} 张卡片",
    }
"""为 T2 (2026-09-07) L1 门禁添加：仅扫描草稿箱、产出每卡错误清单的 lint 函数。"""
from pathlib import Path
from common.frontmatter import try_read_card, validate_card


def lint_drafts(root: Path, platform: str) -> dict:
    """L1 门禁专用：只扫 .sync/drafts/<platform>_draft/（含 candidates/）的草稿卡。

    返回 dict 格式：
      - checked: int  (扫了几张草稿)
      - errors: list  (每张不合规卡 = {name, errors: list[str]})
      - notes: str
    - errors 为空 = 该卡通过门禁，可晋升
    - errors 非空 = 该卡 frontmatter 不合规，sync.ingest 应阻断（hard）或标红（soft）
    """
    drafts = root / ".sync" / "drafts" / f"{platform}_draft"
    out = {"checked": 0, "errors": [], "notes": ""}
    if not drafts.is_dir():
        out["notes"] = f"草稿目录不存在: {drafts}"
        return out
    candidates = []
    candidates.extend(sorted(drafts.glob("*.md")))
    cands = drafts / "candidates"
    if cands.is_dir():
        candidates.extend(sorted(cands.glob("*.md")))
    for p in candidates:
        out["checked"] += 1
        card = try_read_card(p)
        if card is None:
            out["errors"].append({"name": p.name, "errors": ["frontmatter 无法解析"]})
            continue
        errs = validate_card(card)
        if errs:
            out["errors"].append({"name": p.name, "errors": errs})
    out["notes"] = f"扫 {out['checked']} 张草稿，{len(out['errors'])} 张不合规"
    return out