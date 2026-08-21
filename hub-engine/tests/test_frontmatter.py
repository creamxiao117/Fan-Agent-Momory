from common.frontmatter import (
    parse_card,
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
