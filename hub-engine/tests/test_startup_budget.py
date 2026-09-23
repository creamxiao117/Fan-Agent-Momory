"""启动链 30K 预算门禁单测。"""

from pathlib import Path

from scripts.startup_budget import LIMITS, TOTAL_LIMIT, check, main, measure


def test_check_passes_at_exact_caps():
    texts = {name: cap for name, _, cap in LIMITS}
    assert check(texts) == []


def test_check_fails_total_over_30k():
    """分帽合计 29K；单靠顶帽到不了总闸——总闸与分帽独立断言，顶帽时总闸必过。"""
    texts = {name: cap for name, _, cap in LIMITS}
    assert check(texts) == []
    assert sum(c for _, _, c in LIMITS) <= TOTAL_LIMIT
    assert TOTAL_LIMIT == 30000
    # 总闸独立打红：AGENTS 4001 + 其余顶帽 = 30001 > 30000（checker 必须可负样本打红）
    over = {name: cap for name, _, cap in LIMITS}
    over["AGENTS.md"] = 4001
    errs = check(over)
    assert any("总和" in e for e in errs)


def test_check_fails_single_file_cap():
    texts = {name: cap for name, _, cap in LIMITS}
    texts["AGENTS.md"] = 3001
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
