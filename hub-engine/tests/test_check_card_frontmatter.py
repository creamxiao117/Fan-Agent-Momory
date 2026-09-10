"""check_card_frontmatter：提交前门禁的三条路径（合规 / schema 违规 / 游离前置行）"""

from pathlib import Path

from scripts.check_card_frontmatter import check_file


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_valid_card_passes(tmp_path):
    _write(
        tmp_path / "experience" / "ok.md",
        "---\ntype: exp\ntags: [x]\nupdated: '2026-09-11'\nstatus: active\nreuse_count: 0\n---\n\n正文\n",
    )
    errors, _warnings = check_file(tmp_path, "experience/ok.md")
    assert errors == []


def test_illegal_type_and_missing_updated_are_errors(tmp_path):
    _write(
        tmp_path / "experience" / "bad.md",
        "---\ntype: experience\ntags: [x]\nstatus: active\n---\n\n正文\n",
    )
    errors, _ = check_file(tmp_path, "experience/bad.md")
    assert any("type 必须为" in e for e in errors)
    assert any("updated 必填" in e for e in errors)


def test_leading_line_before_frontmatter_is_error(tmp_path):
    """代码头注释放在 --- 之前 → 解析失败、卡不进向量库（2026-09-11 实测形态）"""
    _write(
        tmp_path / "experience" / "lead.md",
        "# @version V1.0 / 注释在 frontmatter 之前\n---\ntype: exp\n---\n\n正文\n",
    )
    errors, _ = check_file(tmp_path, "experience/lead.md")
    assert len(errors) == 1
    assert "不在文件起始处" in errors[0]


def test_dir_type_mismatch_is_warning_not_error(tmp_path):
    """目录与 type 不一致只警告不阻断（experience/ 历史混装多类型）"""
    _write(
        tmp_path / "experience" / "mix.md",
        "---\ntype: rule\ntags: [x]\nupdated: '2026-09-11'\nstatus: active\nreuse_count: 0\n---\n\n正文\n",
    )
    errors, warnings = check_file(tmp_path, "experience/mix.md")
    assert errors == []
    assert any("不一致" in w for w in warnings)
