"""启动链预算门禁单测（L0 四文件 + L1 按任务型）。"""

from pathlib import Path

from scripts.startup_budget import (
    L1_LIMIT,
    LIMITS,
    TOTAL_LIMIT,
    _find_card,
    check,
    check_tiers,
    main,
    measure,
    measure_tiers,
)


def test_check_passes_at_exact_caps():
    texts = {name: cap for name, _, cap in LIMITS}
    assert check(texts) == []
    # 设计不变量：分项帽之和不得超总帽，否则分项帽永远不先触发
    assert sum(c for _, _, c in LIMITS) <= TOTAL_LIMIT


def test_check_fails_total_over_30k():
    """总闸必须可负样本打红（阈值从 LIMITS 派生，不硬编码，抗帽值调整）。"""
    texts = {name: cap for name, _, cap in LIMITS}
    assert check(texts) == []
    assert TOTAL_LIMIT == 30000

    # 仅抬 AGENTS 一项到刚好突破总帽（其余保持顶帽）→ 必须报「总和」错误
    others = sum(c for name, _, c in LIMITS if name != "AGENTS.md")
    over = {name: cap for name, _, cap in LIMITS}
    over["AGENTS.md"] = TOTAL_LIMIT - others + 1
    errs = check(over)
    assert any("总和" in e for e in errs), f"应报总和超限，实际: {errs}"


def test_check_fails_single_file_cap():
    """单文件超分项帽必须被打红（阈值从帽派生）"""
    texts = {name: cap for name, _, cap in LIMITS}
    agents_cap = next(c for name, _, c in LIMITS if name == "AGENTS.md")
    texts["AGENTS.md"] = agents_cap + 1
    errs = check(texts)
    assert any("AGENTS.md" in e for e in errs)


def test_measure_reads_repo_files(tmp_path: Path):
    for _name, rel, _cap in LIMITS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("a" * 10, encoding="utf-8")
    rows = measure(tmp_path)
    assert {r["name"] for r in rows} == {name for name, _, _ in LIMITS}
    assert all(r["chars"] == 10 for r in rows)


def _tier(chars: int, missing: list[str] | None = None, tier: str = "code") -> dict:
    return {"tier": tier, "chars": chars, "count": 1, "missing": missing or []}


def test_check_tiers_passes_within_limit():
    assert check_tiers([_tier(1), _tier(L1_LIMIT, tier="hub")]) == []


def test_check_tiers_flags_over_limit():
    """L1 超 spec S2 声明的 15K 必须报错——此前该声明无任何门禁看守"""
    errs = check_tiers([_tier(L1_LIMIT + 1)])
    assert any("L1[code]" in e for e in errs), f"应报 L1 超限，实际: {errs}"


def test_check_tiers_flags_missing_card():
    """L1 卡名找不到文件比超预算更危险（路由指向不存在的卡）"""
    errs = check_tiers([_tier(100, missing=["no-such-card"])])
    assert any("卡不存在" in e and "no-such-card" in e for e in errs), errs


def test_measure_tiers_l1_names_resolve_to_real_cards():
    """真实仓库：L1_CARDS 里每个卡名都应解析到实际文件（防路由悬空）"""
    rows = measure_tiers()
    assert rows, "应至少含 4 个任务型"
    missing = [m for r in rows for m in r["missing"]]
    assert missing == [], f"L1_CARDS 指向了不存在的卡: {missing}"
    for r in rows:
        assert r["chars"] <= L1_LIMIT, f"L1[{r['tier']}] 已超 {L1_LIMIT}: {r['chars']}"


def test_find_card_searches_authority_dirs(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    (hub / "methodology").mkdir(parents=True)
    (hub / "methodology" / "m-card.md").write_text("x", encoding="utf-8")
    assert _find_card(hub, "m-card") is not None
    assert _find_card(hub, "nope") is None


def test_main_reports_l1_lines(capsys):
    """main() 的输出应包含 L1 行（可观测），且退出码 0"""
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "L1[" in out, f"应打印 L1 分项，实际: {out}"


def test_main_exit_codes(tmp_path: Path, capsys):
    for _name, rel, _cap in LIMITS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 0
    (tmp_path / "AGENTS.md").write_text("x" * 4000, encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "AGENTS.md" in out
