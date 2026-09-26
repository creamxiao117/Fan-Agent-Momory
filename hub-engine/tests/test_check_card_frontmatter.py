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


def test_missing_status_is_error_despite_parse_default(tmp_path):
    """V1.1：raw 层缺 status ⇒ 阻断。

    回归背景（审计 §11.4 D1）：`parse_card` 把缺省 status 兑成 active，于是 6 张卡
    「压根没写 status」在 validate_card 眼里合法、静默存活。
    """
    _write(
        tmp_path / "experience" / "nos.md",
        "---\ntype: exp\ntags: [x]\nupdated: '2026-09-11'\n---\n\n正文\n",
    )
    errors, warnings = check_file(tmp_path, "experience/nos.md")
    assert any("缺必填字段 'status'" in e for e in errors)
    assert warnings == []


def test_missing_type_is_error(tmp_path):
    """同理：type 缺失不能靠 parse_card 的 note 默认值蒙混"""
    _write(
        tmp_path / "experience" / "not.md",
        "---\ntags: [x]\nupdated: '2026-09-11'\nstatus: active\n---\n\n正文\n",
    )
    errors, _ = check_file(tmp_path, "experience/not.md")
    assert any("缺必填字段 'type'" in e for e in errors)


def test_empty_tags_is_warning_not_error(tmp_path):
    """tags 为空不阻断（不丽造标签），但必须提醒：tag 检索/可定位度量看不到该卡"""
    _write(
        tmp_path / "experience" / "notag.md",
        "---\ntype: exp\ntags:\nupdated: '2026-09-11'\nstatus: active\n---\n\n正文\n",
    )
    errors, warnings = check_file(tmp_path, "experience/notag.md")
    assert errors == []
    assert any("tags 为空" in w for w in warnings)
