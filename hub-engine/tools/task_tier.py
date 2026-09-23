# hub-engine/tools/task_tier.py
"""任务分型（spec S2 四型）与 L1 规则卡路由——AGENTS 路由表的代码侧单一事实源。"""

from __future__ import annotations

import re
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
        return (
            re.search(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", text)
            is not None
        )
    return kw in text


_ORDER: tuple[Tier, ...] = ("hub", "sync", "code")

L1_CARDS: dict[Tier, list[str]] = {
    "light": [],
    "code": [
        "chinese-text-encoding-discipline",
        "agent-code-discipline-iron-rule",
        "multi-language-style-config",
    ],
    "hub": [
        "dual-platform-coherence-discipline",
        "global-rules",
        "memory-hub-distill-last",
    ],
    "sync": [
        "cross-platform-sync-rule",
        "dual-platform-coherence-discipline",
    ],
}


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
