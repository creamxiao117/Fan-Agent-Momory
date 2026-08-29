"""全局统一常量 — 各模块从这里引用，避免分散定义导致不一致。"""

# 需要人工审核的卡类型集合：一条坏规则/方法论影响全局行为
HUMAN_REQUIRED_TYPES = frozenset({"rule", "methodology"})

# ingest 流程的高风险类型（与 HUMAN_REQUIRED_TYPES 等价）
# 规则/方法论 → 草稿 ingest 时进 .sync/pending/ 待人工确认
HIGH_RISK = HUMAN_REQUIRED_TYPES

# 各模块自动操作可安全修改的卡类型（非高风险）
LOW_RISK_TYPES = frozenset({"exp", "note", "project", "retro", "blueprint", "longterm"})
