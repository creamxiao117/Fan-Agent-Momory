"""INDEX 渲染器单测：卡文件 → 产物，一致性由 --check 看守（模型同 ruff format --check）。

回归背景（2026-10-01）：INDEX 曾是**手写**枚举 → 与卡数同比增长 → 字符帽永远要人批。
改为渲染产物后，「索引与磁盘一致」必须由门禁看守，且手改必须能被打红。
"""

from pathlib import Path

from scripts.index_consistency import card_slug
from scripts.render_index import (
    FULL_DIRS,
    FULL_NAME,
    L0_NAME,
    check,
    main,
    parse_entries,
    read_indexes,
    render_full,
    write,
)
from tools.hub_registry import CARD_DIRS, scan

# 注意：卡正文首段即摘要（本仓 extract_summary 的口径）——夹具必须遵守，
# 否则拿到的是 H1 标题而非段落摘要（历史坑：09-23 曾因此把半截标题写进 INDEX）。
CARD = """---
type: rule
tags: [demo]
updated: '2026-10-01'
status: active
---

{summary}
"""


def _card(hub: Path, sub: str, slug: str, summary: str) -> Path:
    d = hub / sub
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.md"
    p.write_text(CARD.format(summary=summary), encoding="utf-8")
    return p


def _hub(tmp_path: Path) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    _card(hub, "rules", "demo-rule", "演示摘要一句话。")
    _card(hub, "blueprints", "demo-bp", "蓝图摘要一句话。")
    return hub


def test_full_dirs_excludes_experience():
    """experience 自 09-23 起独立成 INDEX-experience.md，渲染器不接管（避免跨分册改动）"""
    assert "experience" not in FULL_DIRS
    assert set(FULL_DIRS) <= set(CARD_DIRS)


def test_render_full_lines_parse_back_as_entries(tmp_path: Path):
    """渲染行必须能被权威正则解析回来（否则下游 audit/lint 认不出=登记丢失）"""
    text = render_full(scan(_hub(tmp_path)))

    entries = parse_entries(text)

    assert entries == {"demo-rule": "演示摘要一句话。", "demo-bp": "蓝图摘要一句话。"}
    assert card_slug("- demo-rule    演示摘要一句话。") == "demo-rule"


def test_render_falls_back_when_card_has_no_text(tmp_path: Path):
    """空正文卡：退标题 → 退「（无摘要）」，绝不留无法解析的裸登记行"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / "rules").mkdir(parents=True)
    (hub / "rules" / "empty-rule.md").write_text(
        "---\ntype: rule\nstatus: active\nupdated: '2026-10-01'\n---\n\n# 空卡标题\n", encoding="utf-8"
    )

    text = render_full(scan(hub))

    assert "- empty-rule    空卡标题" in text, text
    assert parse_entries(text) == {"empty-rule": "空卡标题"}


def test_render_full_is_deterministic(tmp_path: Path):
    hub = _hub(tmp_path)
    cards = scan(hub)
    assert render_full(cards) == render_full(cards)
    # 顺序按 CARD_DIRS（rules 先于 blueprints），与目录权重无关
    text = render_full(cards)
    assert text.index("demo-rule") < text.index("demo-bp")


def test_check_requires_product_file(tmp_path: Path):
    errs = check(_hub(tmp_path))
    assert any(FULL_NAME in e for e in errs), errs


def test_write_then_check_is_clean(tmp_path: Path):
    hub = _hub(tmp_path)

    assert write(hub) == []
    assert check(hub) == [], "渲染后必须一致"


def test_write_uses_single_writer_lock(tmp_path: Path):
    """写入必须在单写者锁内（L0 安全底座：单一写入者），且用完释放"""
    hub = _hub(tmp_path)
    (hub / ".sync" / "locks").mkdir(parents=True)
    write(hub)
    assert not (hub / ".sync" / "locks" / "writer.lock").exists()


def test_check_detects_hand_edit(tmp_path: Path):
    """手改渲染产物必须被打红——这是替代「人工批帽」的主门禁的关键一环"""
    hub = _hub(tmp_path)
    write(hub)
    target = hub / FULL_NAME
    target.write_text(target.read_text(encoding="utf-8") + "- 手工塞的一行    不该在这\n", encoding="utf-8")

    errs = check(hub)

    assert any("不一致" in e for e in errs), errs
    assert write(hub) == [], "重渲染后应恢复"
    assert check(hub) == []


def test_check_fails_loud_on_broken_card(tmp_path: Path):
    """坏卡 → 派生失败（不得渲染出「少一张卡」的干净产物）"""
    hub = _hub(tmp_path)
    (hub / "rules" / "broken.md").write_text("no frontmatter", encoding="utf-8")

    errs = check(hub)

    assert errs and "broken.md" in errs[0], errs


def test_main_exit_codes(tmp_path: Path, capsys):
    hub = _hub(tmp_path)
    assert main(["--root", str(hub), "--write"]) == 0
    assert main(["--root", str(hub), "--check"]) == 0
    (hub / FULL_NAME).write_text("被手改", encoding="utf-8")
    assert main(["--root", str(hub), "--check"]) == 3
    assert "不一致" in capsys.readouterr().out


def test_report_classifies_annotation_and_stale(tmp_path: Path, capsys):
    """差异分类：人工追加后缀（注释型）vs 卡已改未重建（陈旧型）vs 幽灵/未登记"""
    hub = _hub(tmp_path)
    _card(hub, "rules", "stale-rule", "新的摘要（卡已改）")
    (hub / L0_NAME).write_text(
        "## 规则（rules/）\n"
        "- demo-rule    演示摘要一句话。status=active｜T1 09-29 ✅\n"
        "- stale-rule   旧描述（还没跟着重建）\n"
        "- gone-rule    幽灵登记\n",
        encoding="utf-8",
    )

    assert main(["--root", str(hub), "--report"]) == 0
    out = capsys.readouterr().out
    assert "注释型（人工追加后缀）] 1" in out
    assert "陈旧型（卡已改未重建）] 1" in out
    assert "幽灵登记（旧有/渲染无）] 1" in out
    assert "未登记（渲染有/旧无）] 1" in out


def test_read_indexes_merges_experience_book(tmp_path: Path):
    hub = _hub(tmp_path)
    (hub / L0_NAME).write_text("- a-rule    A 描述\n", encoding="utf-8")
    (hub / "INDEX-experience.md").write_text("- exp-card    经验描述\n", encoding="utf-8")

    assert read_indexes(hub) == {"a-rule": "A 描述", "exp-card": "经验描述"}
