"""L0 形状门禁 + 判据 C1/C2（**取代人工批帽**的主门禁的守护测试）。

背景（2026-10-01）：L0（INDEX.md）只要含与卡数成正比的枚举行，顶帽就是数学必然
（先例 09-23 14k→20k、09-27 20k→22k，各只多撑 1-2 天）。本文件看守的是**形状**：
L0 不得出现 per-card 登记行；行数与卡数解耦。形状断言与卡数无关 → 永不顶帽 → 不需人批。
"""

from pathlib import Path

from scripts.render_index import L0_NAME, render_l0, write
from scripts.startup_budget import LIMITS, check_l0_shape, main
from tools.hub_registry import scan

CARD = """---
type: rule
tags: [demo]
updated: '2026-10-01'
status: active
---

{body}
"""


def _card(hub: Path, sub: str, slug: str, body: str = "一句话摘要。\n") -> None:
    d = hub / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(CARD.format(body=body), encoding="utf-8")


def _hub(tmp_path: Path, n_cards: int = 3) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    for i in range(n_cards):
        _card(hub, "rules", f"rule-{i:03d}")
    return hub


def test_shape_gate_blocks_per_card_line():
    """C2：L0 里出现 per-card 登记行必须被打红（这是替代批帽的主门禁）"""
    errs = check_l0_shape("- rules-routing-table    RULES_ROUTING — 规则路由表（核心）\n")

    assert errs and "per-card" in errs[0]


def test_shape_gate_allows_capability_map_lines():
    """能力图行不是登记行：目录名含 `/` ⇒ 权威正则天然不匹配（不是靠豁免名单）"""
    map_lines = (
        "- rules/          35 张｜示例：dll-version-lock · global-rules\n"
        "- experience/    225 张 → 详见 INDEX-experience.md（L2）\n"
        "1. 执行前先查中枢：确定性读本图 / `INDEX-full.md`\n"
        "> 各平台内容先写入 `.sync/drafts/<platform>_draft/`\n"
    )

    assert check_l0_shape(map_lines) == []


def test_shape_gate_passes_on_real_hub():
    """真实中枢的 L0 必须是形状合规的（当前态守护）"""
    from tools.hub_registry import hub_root

    p = hub_root() / L0_NAME
    if not p.exists():  # pragma: no cover - 单仓环境降级
        return
    assert check_l0_shape(p.read_text(encoding="utf-8")) == []


def test_main_reports_shape_violation(tmp_path: Path, capsys):
    """形状违规必须能让预算门禁非 0 退出（pre-commit 出口 5 才能拦）"""
    hub = _hub(tmp_path)
    for _name, rel, _cap in LIMITS:
        p = tmp_path / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("ok", encoding="utf-8")
    # L0 塞进一条 per-card 登记行
    (hub / L0_NAME).write_text("- some-card    Some 描述\n", encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 1
    assert "SHAPE" in capsys.readouterr().out


def test_c1_l0_line_count_decoupled_from_card_count(tmp_path: Path):
    """C1：卡数增长不得改变 L0 行数（枚举项被移除 ⇒ 与卡数解耦）"""
    hub_small = _hub(tmp_path / "small", n_cards=3)
    hub_big = _hub(tmp_path / "big", n_cards=60)

    small = render_l0(scan(hub_small))
    big = render_l0(scan(hub_big))

    assert len(small.splitlines()) == len(big.splitlines())
    # 字符数允许数量位数的微小差异，但必须在 ±5% 内（不是随卡数线性增长）
    assert abs(len(big) - len(small)) <= 0.05 * len(small)


def test_c1_l0_has_no_card_slugs(tmp_path: Path):
    """C1 必要条件：L0 里不得出现任何卡的 slug 作为登记行"""
    hub = _hub(tmp_path, n_cards=5)

    text = render_l0(scan(hub))

    assert check_l0_shape(text) == []
    for slug in ("rule-000", "rule-004"):
        assert f"- {slug}" not in text


def test_write_then_check_covers_l0(tmp_path: Path):
    """写入产物包含 L0；手改 L0 必须被 --check 抓到"""
    from scripts.render_index import check

    hub = _hub(tmp_path)
    assert write(hub) == []
    assert check(hub) == []

    (hub / L0_NAME).write_text("被手改的 L0", encoding="utf-8")
    errs = check(hub)
    assert any(L0_NAME in e for e in errs), errs
