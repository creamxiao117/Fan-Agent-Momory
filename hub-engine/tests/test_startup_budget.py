"""启动链 30K 预算门禁单测。"""

from pathlib import Path

from scripts.startup_budget import LIMITS, TOTAL_LIMIT, check, main, measure


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
