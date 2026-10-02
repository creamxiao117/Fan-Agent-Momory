r"""任务分型与检索范围 —— **唯一事实源**（口径统一，2026-10-02 裁定）。

## 为何重写（这是"两套分型"的根治）

此前仓内**并存两套分型**，键集不相交、知识重复：

| 套 | 位置 | 取值 | 用途 |
|---|---|---|---|
| A | 本模块 | `light \| code \| hub \| sync` | AGENTS 路由 → 补读哪些 L1 卡 |
| B | `tools/mcp_handlers.TASK_KIND_TYPES` | `dll \| code \| project \| debug \| ideation \| generic` | `hub_bootstrap` → 检索哪些子区 |

后果：加一个型要改两处；pi 接入时必然会写出第三套（本仓已三次复发"手写枚举→漂移"：
L0 INDEX 枚举行 / `L1_CARDS` 清单 / `tier` 覆盖 7%）。

## 现在的一张表

- `Tier` —— **规范型**（`classify()` 的返回域，`AGENTS.md` 路由依据）。新增 `project`
  （立项/蓝图），因为「立项必查蓝图」是 `rules/global-rules.md` 的铁律，
  不能因归一而丢失。
- `TIER_SCOPE` —— 型 → 检索子区（`hub_bootstrap` 的取数口径）。这是型**派生**出的范围。
- `LEGACY_KIND_SCOPE` / `LEGACY_KIND_ALIAS` —— 旧 `task_kind` 的**入参兼容层**：
  取值与迁移前快照**逐值相等**（由 `tests/test_task_tier.py::test_legacy_kind_types_unchanged`
  锁死），故既有调用方（trae / mavis / deepseek / workbuddy / 文档）**零行为回归**。
- `scope_for()` / `resolve_kind()` —— **唯一解析入口**。任何新代码不得自行拼子区清单。

## 命名避坑

不要复用 `L0/L1/L2` 作为等级名——它们已被 `scripts/startup_budget.py` 占为**预算分层**
（L0 常驻 / L1 按型 / L2 检索）。记忆可信度分级另开 `grade` 轴（见架构重构计划 M1）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

Tier = Literal["light", "code", "hub", "sync", "project"]

# ── 唯一表 ①：规范型 → 检索子区 ─────────────────────────────────
# light = 不检索（`scope_for("light")` 返回空元组；hub_bootstrap 对 light 短路且不写审计）
TIER_SCOPE: dict[Tier, tuple[str, ...]] = {
    "light": (),
    "code": ("rules", "methodology", "projects"),
    "hub": ("rules", "methodology", "experience"),
    "sync": ("rules", "methodology"),
    "project": ("longterm", "methodology", "blueprints"),
}

# ── 唯一表 ②：旧 task_kind 兼容层（取值 = 2026-10-02 迁移前快照，逐值不变）──
# 为何保留独立取值而不并入所属型的 TIER_SCOPE：迁移前 `debug` 只查 projects+experience、
# `dll` 只查 rules+projects，都是**有意收窄**的（少注入 = 少 token）。归一会放宽它们，
# 属行为变更，不在"口径统一"的授权范围内。故此处只做「别名 + 原范围」登记，
# 让漂移可见、改动集中在一处（想收窄/放宽只改这张表）。
LEGACY_KIND_SCOPE: dict[str, tuple[str, ...]] = {
    "dll": ("rules", "projects"),
    "code": ("rules", "methodology", "projects"),
    "project": ("longterm", "methodology", "blueprints"),
    "debug": ("projects", "experience"),
    "ideation": ("blueprints", "methodology", "experience"),
    "generic": ("rules", "methodology", "longterm", "projects"),
}

# 旧名 → 规范型（供 resolve_kind 报告与统计；`dll`/`debug` 都是 `code` 的领域特例）
LEGACY_KIND_ALIAS: dict[str, Tier] = {
    "dll": "code",
    "code": "code",
    "debug": "code",
    "project": "project",
    "ideation": "project",
    "generic": "hub",
    # 规范型名同时是合法入参（幂等）
    "light": "light",
    "hub": "hub",
    "sync": "sync",
}

# 未知名字的兜底：保持迁移前行为（`generic` 的宽范围）
FALLBACK_KIND = "generic"


def resolve_kind(name: str) -> Tier:
    """任意分型名 → 规范型。未知名回退 `hub`（= 旧 `generic` 的所属型）。"""
    key = (name or "").strip().lower()
    if key in LEGACY_KIND_ALIAS:
        return LEGACY_KIND_ALIAS[key]
    if key in TIER_SCOPE:
        return key  # type: ignore[return-value]
    return "hub"


def scope_for(name: str) -> tuple[str, ...]:
    """**唯一取数入口**：任意分型名 → 检索子区。

    解析顺序（保持迁移前行为）：
      1) 旧 task_kind 名（`dll`/`debug`/`ideation`/`generic` …）→ 其登记范围
      2) 规范型名（`light`/`code`/`hub`/`sync`/`project`）→ `TIER_SCOPE`
      3) 未知 → `generic` 的宽范围
    """
    key = (name or "").strip().lower()
    if key in LEGACY_KIND_SCOPE:
        return LEGACY_KIND_SCOPE[key]
    if key in TIER_SCOPE:
        return TIER_SCOPE[key]  # type: ignore[index]
    return LEGACY_KIND_SCOPE[FALLBACK_KIND]


# ── 派生视图：旧常量由表渲染（单一事实源；消费方零改动）──────────
# 保留本名以兼容既有 import（mcp_handlers / tests / 文档）——
# 但**取值只能来自上面两张表**，此处不得出现任何手写字面量。
TASK_KIND_TYPES: dict[str, tuple[str, ...]] = {k: scope_for(k) for k in LEGACY_KIND_SCOPE}


# ── 关键词分型 ────────────────────────────────────────────────
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
    # project 置于最后：仅在 hub/sync/code 都不命中时才判为立项型（保守，不改既有判定）
    "project": (
        "立项",
        "蓝图",
        "选型",
        "新项目",
        "技术路径",
        "方案对比",
        "ideation",
    ),
}


def _hit(kw: str, text: str) -> bool:
    # 纯 ASCII 单词关键词用词边界匹配：覆盖句末 PR / 裸 rules，且不误伤嵌入词（如 approve）
    if kw.isascii() and kw.isalnum():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", text) is not None
    return kw in text


_ORDER: tuple[Tier, ...] = ("hub", "sync", "code", "project")

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
    out: dict[Tier, list[str]] = {t: [] for t in TIER_SCOPE}
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


__all__ = [
    "FALLBACK_KIND",
    "L1_MAX_CARDS_PER_TIER",
    "L1_TIER_FIELD",
    "LEGACY_KIND_ALIAS",
    "LEGACY_KIND_SCOPE",
    "TASK_KIND_TYPES",
    "TIER_SCOPE",
    "Tier",
    "check_l1_shape",
    "classify",
    "l1_cards",
    "resolve_kind",
    "scope_for",
]
