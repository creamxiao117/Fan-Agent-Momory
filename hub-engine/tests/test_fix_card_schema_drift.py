"""fix_card_schema_drift 单测：非法 type / updated 取 created / dry-run / 需人工 / 高风险跳过"""

from pathlib import Path

from scripts.fix_card_schema_drift import run_fix


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_repairs_illegal_type_and_fills_updated_from_created(tmp_path):
    """type 非法值按目录映射；updated 取 created（不盖成今天）；正文不动"""
    _write(
        tmp_path / "experience" / "t.md",
        "---\ntype: experience\ntags: [x]\ncreated: 2026-09-10\nstatus: draft\n---\n\n正文甲\n",
    )
    res = run_fix(tmp_path, apply=True)
    assert res["fixed"] == 1
    text = (tmp_path / "experience" / "t.md").read_text(encoding="utf-8")
    assert "type: exp" in text
    assert "status: active" in text
    assert "updated: '2026-09-10'" in text
    assert "正文甲" in text


def test_dry_run_does_not_write(tmp_path):
    p = tmp_path / "experience" / "t.md"
    _write(p, "---\ntype: experience\ntags: [x]\ncreated: 2026-09-10\n---\n\n正文乙\n")
    before = p.read_text(encoding="utf-8")
    res = run_fix(tmp_path, apply=False)
    assert res["fixed"] == 1
    assert p.read_text(encoding="utf-8") == before


def test_reports_missing_frontmatter_as_manual(tmp_path):
    """无 frontmatter → 不臆造，列入需人工"""
    _write(tmp_path / "experience" / "bad.md", "# 无 frontmatter\n\n正文\n")
    res = run_fix(tmp_path, apply=True)
    assert res["fixed"] == 0
    assert res["skipped"] == 1
    assert "游离前置行" in res["skipped_details"][0][1]


def test_skips_high_risk_dirs_by_default(tmp_path):
    """rules/ methodology/ 默认跳过；--include-high-risk 才处理"""
    _write(tmp_path / "rules" / "r.md", "---\ntype: experience\ntags: [x]\n---\n\n正文丙\n")
    assert run_fix(tmp_path, apply=True)["fixed"] == 0
    assert run_fix(tmp_path, apply=True, include_high_risk=True)["fixed"] == 1


def test_clean_card_untouched(tmp_path):
    _write(
        tmp_path / "experience" / "ok.md",
        "---\ntype: exp\ntags: [x]\nupdated: '2026-09-10'\nstatus: active\nreuse_count: 0\n---\n\n正文丁\n",
    )
    res = run_fix(tmp_path, apply=True)
    assert res["fixed"] == 0
    assert res["clean"] == 1


def test_fills_missing_status(tmp_path):
    """V1.1：缺 status 的卡要能被修（修复前它在 validate_card 眼里完全合法）

    回归背景（审计 §11.4 D1）：experience/ 下 6 张卡缺 status，本工具旧版把它们
    计入「合规」直接跳过 ⇒ 门禁报错却无法一键修。
    """
    p = tmp_path / "experience" / "nos.md"
    _write(p, "---\ntype: exp\ntags: [x]\nupdated: '2026-09-10'\n---\n\n正文戊\n")
    res = run_fix(tmp_path, apply=True)
    assert res["fixed"] == 1
    text = p.read_text(encoding="utf-8")
    assert "status: active" in text
    assert "正文戊" in text


def test_deprecated_status_not_flipped_when_repairing_type(tmp_path):
    """V1.1：本地 VALID_STATUS 副本漏了 deprecated ⇒ 修 type 时会把 deprecated 错改成 active"""
    p = tmp_path / "experience" / "dep.md"
    _write(
        p,
        "---\ntype: experience\ntags: [x]\nupdated: '2026-09-10'\nstatus: deprecated\n---\n\n正文己\n",
    )
    run_fix(tmp_path, apply=True)
    text = p.read_text(encoding="utf-8")
    assert "type: exp" in text
    assert "status: deprecated" in text
