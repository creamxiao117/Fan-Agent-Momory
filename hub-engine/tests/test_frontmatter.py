from common.frontmatter import (
    missing_required_keys,
    parse_card,
    raw_frontmatter,
    read_card,
    save_card,
    validate_card,
    write_card,
)

SAMPLE = """---
type: rule
tags:
  - autocad
  - dll-lock
updated: 2026-08-17
status: active
reuse_count: 0
---
# AutoCAD DLL 版本命名（防文件锁）
每次修改 DLL 后必须递增版本号。
"""


def test_parse_roundtrip():
    card = parse_card(SAMPLE)
    assert card.type == "rule"
    assert card.tags == ["autocad", "dll-lock"]
    assert card.status == "active"
    assert card.reuse_count == 0
    assert "# AutoCAD" in card.body


# ---- raw_frontmatter / missing_required_keys（V1.1：缺失字段的 raw 层判定）----


def test_missing_required_keys_flags_absent_and_empty(tmp_path):
    """缺失与空值同罪；标签不在必填内（空 tags 只算警告）"""
    assert missing_required_keys({"type": "exp", "status": "active", "updated": "2026-09-25"}) == []
    assert missing_required_keys({"type": "exp", "status": "", "updated": None}) == ["status", "updated"]
    assert missing_required_keys({}) == ["type", "status", "updated"]


def test_raw_frontmatter_reads_without_defaults(tmp_path):
    """raw 层不能带默认值（这正是它存在的理由：parse_card 会补 status=active）"""
    p = tmp_path / "c.md"
    p.write_text("---\ntype: exp\nupdated: '2026-09-25'\n---\n\n正文\n", encoding="utf-8")
    raw = raw_frontmatter(p)
    assert "status" not in raw
    assert missing_required_keys(raw) == ["status"]


def test_raw_frontmatter_tolerates_bom_and_blank_lines(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("\ufeff\n---\ntype: exp\n---\n\n正文\n", encoding="utf-8")
    assert raw_frontmatter(p) == {"type": "exp"}


def test_raw_frontmatter_returns_empty_on_unparsable(tmp_path):
    """四类读不到的输入一律 {}（不抛异常：它是门禁的前置探测）"""
    assert raw_frontmatter(tmp_path / "不存在.md") == {}
    no_fm = tmp_path / "nofm.md"
    no_fm.write_text("# 无 frontmatter\n", encoding="utf-8")
    assert raw_frontmatter(no_fm) == {}
    unterminated = tmp_path / "half.md"
    unterminated.write_text("---\ntype: exp\n", encoding="utf-8")
    assert raw_frontmatter(unterminated) == {}
    not_dict = tmp_path / "list.md"
    not_dict.write_text("---\n- a\n- b\n---\n\n正文\n", encoding="utf-8")
    assert raw_frontmatter(not_dict) == {}


def test_write_roundtrip_preserves_fields():
    card = parse_card(SAMPLE)
    text = write_card(card)
    again = parse_card(text)
    assert again.type == card.type
    assert again.tags == card.tags
    assert again.body == card.body


def test_validate_ok():
    assert validate_card(parse_card(SAMPLE)) == []


def test_validate_bad_type_and_missing_updated():
    card = parse_card(SAMPLE)
    card.type = "unknown"
    card.updated = ""
    errs = validate_card(card)
    assert any("type" in e for e in errs)
    assert any("updated" in e for e in errs)


def test_save_and_read(tmp_path):
    p = tmp_path / "a.md"
    save_card(parse_card(SAMPLE), p)
    card = read_card(p)
    assert card.type == "rule"
    assert card.path == p


def test_parse_missing_frontmatter_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_card("没有 frontmatter 的纯文本")


def test_read_card_tolerates_bom(tmp_path):
    """带 BOM（EF BB BF）的卡应正常解析，不误判 invalid（实测草稿默认 UTF8 会带 BOM）"""
    p = tmp_path / "bom.md"
    p.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
    card = read_card(p)
    assert card.type == "rule"
    assert card.tags == ["autocad", "dll-lock"]
