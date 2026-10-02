from pathlib import Path

# hub-engine/tests/test_task_tier.py
from tools.task_tier import (
    LEGACY_KIND_SCOPE,
    TASK_KIND_TYPES,
    TIER_SCOPE,
    check_l1_shape,
    classify,
    l1_cards,
    resolve_kind,
    scope_for,
)

# 迁移基准快照（2026-10-02，口径统一**之前**的 TASK_KIND_TYPES 逐值快照）。
# 用途：证明「统一 = 单表 + 别名登记」，而非偷偷改行为——legacy 键取值必须一字不差。
LEGACY_KIND_SNAPSHOT = {
    "dll": ("rules", "projects"),
    "code": ("rules", "methodology", "projects"),
    "project": ("longterm", "methodology", "blueprints"),
    "debug": ("projects", "experience"),
    "ideation": ("blueprints", "methodology", "experience"),
    "generic": ("rules", "methodology", "longterm", "projects"),
}

# 迁移基准快照（2026-10-01）：**手写清单退出前**的最后状态。
# 用途：证明「派生集合 == 手写集合」（迁移零漂移），而不是凭感觉切换。
LEGACY_L1_CARDS = {
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


def test_derived_l1_equals_legacy_map():
    """迁移正确性证明：由卡 frontmatter 派生的集合 == 手写清单（集合相等，顺序无关）

    回归背景：L1 卡集合曾是手写枚举（与 L0 INDEX 同病：枚举 + 固定帽 ⇒ 必然顶帽）。
    改为卡自己声明 `l1_tier` 后，必须证「一张不多、一张不少」。
    """
    derived = l1_cards()
    assert derived, "应至少能派生出 L1 卡（检查卡 frontmatter 的 l1_tier 字段）"
    for tier, slugs in LEGACY_L1_CARDS.items():
        assert sorted(derived.get(tier, [])) == sorted(slugs), f"L1[{tier}] 派生集合与迁移基准不一致"


def test_l1_shape_within_cap():
    """形状断言：单型 ≤3 张（新增必须挤掉一张，不靠人批帽）"""
    assert check_l1_shape(l1_cards()) == []


def test_l1_shape_flags_over_cap():
    from tools.task_tier import L1_MAX_CARDS_PER_TIER

    over = {"code": [f"card-{i}" for i in range(L1_MAX_CARDS_PER_TIER + 1)]}
    errs = check_l1_shape(over)
    assert errs and "L1[code]" in errs[0]


def test_l1_cards_missing_hub_is_empty(tmp_path):
    """中枢缺失时降级为空（不是失败）——与 startup_budget 口径一致"""
    empty = {"light": [], "code": [], "hub": [], "sync": [], "project": []}
    assert l1_cards(tmp_path / "nowhere") == empty


def test_l1_cards_multi_tier_card(tmp_path):
    """一张卡可声明多个任务型（如双平台一致性卡同属 hub 与 sync）"""
    rules = tmp_path / "AgentMemoryHub" / "rules"
    rules.mkdir(parents=True)
    (rules / "multi.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: '2026-10-01'\nstatus: active\nl1_tier: [hub, sync]\n---\n\n# x\n",
        encoding="utf-8",
    )
    derived = l1_cards(tmp_path / "AgentMemoryHub")
    assert derived["hub"] == ["multi"] and derived["sync"] == ["multi"]


def test_default_is_light():
    assert classify("今天天气怎么样") == "light"
    assert classify("") == "light"


def test_code_keywords():
    assert classify("帮我 commit 这个改动并跑 ruff") == "code"
    assert classify("修一下这个 patch 的缩进") == "code"
    assert classify("open a PR for this fix") == "code"


def test_hub_keywords():
    assert classify("把经验 ingest 进中枢 rules") == "hub"
    assert classify("查一下 AgentMemoryHub 的 INDEX") == "hub"


def test_sentence_final_pr_is_code():
    # S2 回归：句末 PR 不再依赖尾随空格
    assert classify("merge the PR") == "code"


def test_bare_rules_is_hub():
    # S2 回归：裸 rules（非 rules/ 路径）也应命中 hub
    assert classify("please follow the rules") == "hub"


def test_sync_keywords():
    assert classify("sync --push 到四个平台") == "sync"
    assert classify("把指令注入 workbuddy") == "sync"


def test_explicit_beats_keyword():
    # 多关键词冲突时：hub > sync > code > light 的固定优先级
    assert classify("ingest 之后 commit 并 sync --push") == "hub"


def test_l1_covers_all_tiers():
    cards = l1_cards()
    for t in ("light", "code", "hub", "sync"):
        assert t in cards
    assert cards["light"] == []  # 仅 L0
    assert any("encoding" in c for c in cards["code"])
    assert "dual-platform-coherence-discipline" in cards["hub"]
    assert "cross-platform-sync-rule" in cards["sync"]


# ── 口径统一（2026-10-02）新增契约 ─────────────────────────────


def test_legacy_kind_types_unchanged():
    """迁移零漂移：legacy task_kind 的取数范围逐值等于迁移前快照。

    （同 LEGACY_L1_CARDS 的证明手法：先锁旧值，再切实现，避免"统一"变成偷偷改行为。）
    """
    assert dict(TASK_KIND_TYPES) == LEGACY_KIND_SNAPSHOT
    assert dict(LEGACY_KIND_SCOPE) == LEGACY_KIND_SNAPSHOT


def test_tier_scope_is_single_source():
    """TASK_KIND_TYPES 必须是**派生物**：与两张表逐值一致，且不含额外键。"""
    derived = {k: scope_for(k) for k in LEGACY_KIND_SCOPE}
    assert derived == TASK_KIND_TYPES
    # 规范型名也走同一入口
    for tier, scope in TIER_SCOPE.items():
        assert scope_for(tier) == scope, f"{tier} 取数范围与 TIER_SCOPE 不一致"


def test_mcp_handlers_no_longer_defines_taxonomy():
    """防复发：分型知识不得回到 mcp_handlers（否则又是两套）。"""
    import tools.mcp_handlers as H

    assert not hasattr(H, "TASK_KIND_TYPES"), "mcp_handlers 不应再定义/转出分型表"
    src = Path(H.__file__).read_text(encoding="utf-8") if H.__file__ else ""
    for legacy_key in LEGACY_KIND_SNAPSHOT:
        assert f'"{legacy_key}": (' not in src, f"mcp_handlers 里又出现了 `{legacy_key}` 的手写范围"


def test_five_tiers_defined():
    assert set(TIER_SCOPE) == {"light", "code", "hub", "sync", "project"}
    assert TIER_SCOPE["light"] == (), "light = 不检索"
    assert scope_for("light") == ()


def test_resolve_kind_maps_legacy_names():
    assert resolve_kind("dll") == "code"
    assert resolve_kind("debug") == "code"
    assert resolve_kind("ideation") == "project"
    assert resolve_kind("generic") == "hub"
    assert resolve_kind("project") == "project"
    assert resolve_kind("whatever") == "hub", "未知回退 generic 的所属型"


def test_classify_project_tier():
    assert classify("给新项目立项，先做技术路径选型") == "project"
    assert classify("按蓝图选型：方案对比") == "project"
    # 既有优先级不变：hub/sync/code 仍先于 project
    assert classify("立项之后 commit 并跑 ruff") == "code"
    assert classify("把立项经验 ingest 进中枢") == "hub"


def test_project_tier_is_not_in_l1_cards_by_default():
    """新增型不得自动带 L1 卡（L1 由卡自身 l1_tier 声明，不能凭空造）。"""
    assert l1_cards()["project"] == []
