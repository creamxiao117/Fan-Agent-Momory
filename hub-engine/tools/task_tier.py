# hub-engine/tools/task_tier.py
"""任务分型（spec S2 四型）与 L1 规则卡路由——AGENTS 路由表的代码侧单一事实源。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

Tier = Literal["light", "code", "hub", "sync"]

# 关键词 → 型；classify 时按 _ORDER 优先级，同型命中即返回
_KEYWORDS: dict[Tier, tuple[str, ...]] = {
    "hub": (
        "中枢",
        "ingest",
        "rules",
        "experience/",
        "methodology",
        "agentmemoryhub",
        "回写",
        "confirm ",
    ),
    "sync": ("sync", "push", "注入", "inject", "platform_bridge", "跨平台"),
    "code": (
        "commit",
        "ruff",
        "pytest",
        "patch",
        "pr",
        "push 代码",
        "refactor",
        "修 bug",
        "改代码",
    ),
}


def _hit(kw: str, text: str) -> bool:
    # 纯 ASCII 单词关键词用词边界匹配：覆盖句末 PR / 裸 rules，且不误伤嵌入词（如 approve）
    if kw.isascii() and kw.isalnum():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", text) is not None
    return kw in text


_ORDER: tuple[Tier, ...] = ("hub", "sync", "code")

# ── L1 卡集合：由**卡自身 frontmatter `l1_tier`** 派生（2026-10-01）────────────
#
# 为何不再手写 `L1_CARDS` 清单（历史先例：L0 INDEX 枚举）：
#   1. 手写枚举 = 与卡数同病——即便有 15K 帽，也会随卡片增长慢慢顶帽；
#   2. 新增/退役 L1 卡要改两处（卡 + 清单），必然漂移；
#   3. 门禁（startup_budget）要“卡不存在必报”，而清单本身就是漂移源。
# 故改为：卡自己声明“我属于哪个任务型”（可多值：list），派生集合即是真相。
#
# 字段名用 `l1_tier` 而**不是** `tier`：卡 frontmatter 已有 `tier: task|iron`（重要度），
# 语义不同，不得覆用。
L1_TIER_FIELD = "l1_tier"

# 单型卡数上限（形状断言，防「顺手再加一张」复发成 L1 ratchet）
L1_MAX_CARDS_PER_TIER = 3


def l1_cards(root: Path | None = None) -> dict[Tier, list[str]]:
    """每个任务型要补读的 L1 卡 slug（按 slug 升序，稳定可复现）。

    降级：中枢缺失/无 rules 目录 → 各型空列表（与 startup_budget 同口径：
    “中枢未就位”不是预算超帽）。
    """
    from pathlib import Path as _P

    from common.frontmatter import try_read_card

    base = _P(root) if root is not None else _P(__file__).resolve().parents[2] / "AgentMemoryHub"
    rules = base / "rules"
    out: dict[Tier, list[str]] = {t: [] for t in ("light", "code", "hub", "sync")}
    if not rules.is_dir():
        return out
    for p in sorted(rules.glob("*.md")):
        card = try_read_card(p)
        if card is None:
            continue
        declared = card.extra.get(L1_TIER_FIELD)
        tiers = declared if isinstance(declared, list) else [declared] if declared else []
        for t in tiers:
            if isinstance(t, str) and t in out and t != "light":
                out[t].append(p.stem)
    for t in out:
        out[t] = sorted(set(out[t]))
    return out


def check_l1_shape(tier_cards: dict[Tier, list[str]]) -> list[str]:
    """L1 形状断言：单型卡数 ≤ L1_MAX_CARDS_PER_TIER（超即违规，空列表=通过）。

    为何要：L1 同样是「枚举 + 固定帽」结构，不看守就会重演 L0 的顶帽循环。
    """
    errs: list[str] = []
    for tier, slugs in tier_cards.items():
        if len(slugs) > L1_MAX_CARDS_PER_TIER:
            errs.append(
                f"L1[{tier}] 卡数 {len(slugs)} > {L1_MAX_CARDS_PER_TIER}（新增须挤掉一张：删旧卡的 l1_tier 字段）"
            )
    return errs


def classify(prompt: str) -> Tier:
    """显式/关键词判定；判不出返回 light。只升不降由调用方在会话内保持。"""
    text = (prompt or "").lower()
    if not text.strip():
        return "light"
    for tier in _ORDER:
        for kw in _KEYWORDS[tier]:
            if _hit(kw.lower(), text):
                return tier
    return "light"
