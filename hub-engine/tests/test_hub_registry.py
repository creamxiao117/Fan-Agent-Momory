"""派生层（tools/hub_registry）单测：纯扫描 + loud-fail。

回归背景（2026-10-01）：ghost/orphan/misrouted 三个漂移维度退役后，坏卡若被静默
跳过，「卡在派生视图里消失」将无任何门禁可见——故 loud-fail 是本模块的核心契约。
"""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tools.hub_registry import (
    CARD_DIRS,
    CardMeta,
    RegistryError,
    by_dir,
    example_slugs,
    hub_root,
    scan,
)

CARD = """---
type: rule
tags: [demo, 示例]
updated: '{updated}'
status: active
reuse_count: {reuse}
---

# {title}

第一段即摘要（本仓卡的写作规范）。
"""


def _card(
    path: Path,
    title: str = "示例卡",
    reuse: int = 0,
    *,
    updated: str = "2026-10-01",
    extra_fm: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CARD.format(title=title, reuse=reuse, updated=updated) + extra_fm, encoding="utf-8")
    return path


def test_scan_reads_card_metadata(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "demo-rule.md", title="演示规则", reuse=3)

    rows = scan(hub)

    assert [c.slug for c in rows] == ["demo-rule"]
    c = rows[0]
    assert c.dir == "rules"
    assert c.rel_path == "rules/demo-rule.md"
    assert c.type == "rule"
    assert c.status == "active"
    assert c.updated == "2026-10-01"
    assert c.reuse_count == 3
    assert c.tags == ("demo", "示例")
    assert c.title == "演示规则"
    assert c.summary, "摘要必须来自卡自身正文（extract_summary）"


def test_scan_fails_loud_on_unparseable_card(tmp_path: Path):
    """坏 frontmatter 必须抛错并列名——不得静默跳过（三种漂移维度退役后的兜底）"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "good-rule.md")
    (hub / "rules" / "broken-rule.md").write_text("no frontmatter here", encoding="utf-8")

    with pytest.raises(RegistryError) as ei:
        scan(hub)

    msg = str(ei.value)
    assert "broken-rule.md" in msg
    assert "good-rule.md" not in msg, "合法卡不应出现在错误清单里"


def test_scan_fails_loud_on_invalid_card(tmp_path: Path):
    """能解析但校验不过（缺 updated / 非法 type）同样是硬错误"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "bad-rule.md", extra_fm="")
    (hub / "rules" / "bad-rule.md").write_text(
        "---\ntype: 不存在的类型\nstatus: active\nupdated: '2026-10-01'\n---\n\n# x\n",
        encoding="utf-8",
    )

    with pytest.raises(RegistryError) as ei:
        scan(hub)

    assert "bad-rule.md" in str(ei.value)
    assert "type" in str(ei.value)


def test_scan_reports_all_bad_cards_at_once(tmp_path: Path):
    """一次列全部坏卡（便于一次修完，而不是修一张跑一次）"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / "rules").mkdir(parents=True)
    (hub / "rules" / "a.md").write_text("broken", encoding="utf-8")
    (hub / "rules" / "b.md").write_text("broken too", encoding="utf-8")

    with pytest.raises(RegistryError) as ei:
        scan(hub)

    assert "a.md" in str(ei.value) and "b.md" in str(ei.value)


def test_scan_skips_non_card_files(tmp_path: Path):
    """log.md / lint-report-*.md / INDEX*.md 不是卡，不参与派生也不报错"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "real-rule.md")
    (hub / "rules" / "log.md").write_text("时间线，无 frontmatter", encoding="utf-8")
    (hub / "rules" / "lint-report-2026-10-01.md").write_text("报告", encoding="utf-8")
    (hub / "rules" / "INDEX-blueprints.md").write_text("渲染产物", encoding="utf-8")

    assert [c.slug for c in scan(hub)] == ["real-rule"]


def test_scan_order_is_stable(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "blueprints" / "b-card.md")
    _card(hub / "rules" / "r-card.md")
    _card(hub / "rules" / "a-card.md")

    assert [(c.dir, c.slug) for c in scan(hub)] == [
        ("rules", "a-card"),
        ("rules", "r-card"),
        ("blueprints", "b-card"),
    ]


def test_scan_missing_hub_is_empty(tmp_path: Path):
    """整个中枢缺失不是「坏卡」：返回空列表，不当失败（与 startup_budget 降级口径一致）"""
    assert scan(tmp_path / "nowhere") == []


def test_by_dir_groups_in_card_dirs_order(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "blueprints" / "b.md")
    _card(hub / "rules" / "r.md")

    grouped = by_dir(scan(hub))

    assert list(grouped) == ["rules", "blueprints"]
    assert [c.slug for c in grouped["rules"]] == ["r"]


def test_example_slugs_is_churn_independent(tmp_path: Path):
    """L0 示例必须是**卡集合的纯函数**：reuse_count / updated 变动不得改变渲染结果。

    回归背景（2026-10-02 实测，这是渲染门禁例行变红的真根因）：示例曾按 reuse_count
    降序选择，而 reuse_count 由 MCP 命中自动 +1（日常数据扰动）⇒ 一次自增就让
    `render_index --check` 变红 ⇒ 阻断**每一次**中枢提交 ⇒ 实际效果是
    训练所有人用 `--no-verify`，从而让全部提交门禁一起失效。
    """
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "alpha.md", reuse=0, updated="2026-01-01")
    _card(hub / "rules" / "beta.md", reuse=9, updated="2026-12-31")
    _card(hub / "rules" / "gamma.md", reuse=5, updated="2026-06-01")

    before = example_slugs(scan(hub), "rules", n=2)
    # 模拟日常扰动：所有使用计数与修改时间都变了
    _card(hub / "rules" / "alpha.md", reuse=99, updated="2026-12-31")
    _card(hub / "rules" / "beta.md", reuse=0, updated="2026-01-01")
    _card(hub / "rules" / "gamma.md", reuse=0, updated="2026-01-01")

    assert example_slugs(scan(hub), "rules", n=2) == before
    assert before == ["alpha", "beta"], "只按 slug 升序取前 n"


def test_example_slugs_unknown_dir_is_empty(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    _card(hub / "rules" / "r.md")
    assert example_slugs(scan(hub), "not-a-dir") == []


def test_scan_real_hub_matches_filesystem_count():
    """真实中枢：派生卡数 == 物理文件数（少一张即漏卡，多一张即误收）"""
    root = hub_root()
    if not (root / "rules").is_dir():  # pragma: no cover - 单仓环境降级
        pytest.skip("无嵌套中枢仓")

    rows = scan(root)
    physical = sum(len(list((root / d).glob("*.md"))) for d in CARD_DIRS if (root / d).is_dir())
    excluded = sum(
        1
        for d in CARD_DIRS
        if (root / d).is_dir()
        for p in (root / d).glob("*.md")
        if p.name == "log.md" or p.name.startswith(("lint-report-", "INDEX"))
    )

    assert len(rows) == physical - excluded
    assert len(rows) > 400, f"真实中枢卡数异常偏少: {len(rows)}"


def test_card_meta_is_frozen():
    meta = CardMeta(slug="s", rel_path="r", dir="d", type="rule", status="active", updated="2026-10-01")
    with pytest.raises(FrozenInstanceError):
        meta.slug = "x"  # type: ignore[misc]
