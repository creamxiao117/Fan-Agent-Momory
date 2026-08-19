from tools.compress import compress_card_text

_CARD = """---
type: blueprint
tags: [skill, governance]
updated: 2026-08-19
status: active
anti_trigger: [安装]
---

# 标题

这是开头导语，介绍卡片主旨。

## 不适用

这里记录禁止命中的场景。

## 示例

```python
print("keep me")
```

## 核心

这段是真正要保留的知识正文。

## 其他小节

更多内容。
"""


def test_level0_is_identity():
    assert compress_card_text(_CARD, 0) == _CARD


def test_level1_folds_blank_lines():
    out = compress_card_text(_CARD, 1)
    # frontmatter 与代码块原样保留
    assert "anti_trigger: [安装]" in out
    assert 'print("keep me")' in out
    # 连续空行被折叠（原文没有连续空行，构造带连续空行的输入验证）
    src = "a\n\n\n\nb"
    assert compress_card_text(src, 1) == "a\n\nb"


def test_level2_drops_negative_section_keeps_core():
    out = compress_card_text(_CARD, 2)
    assert "不适用" not in out
    assert "禁止命中" not in out
    assert "知识正文" in out  # 核心知识保留
    assert "开头导语" in out


def test_level4_drops_examples_but_keeps_code_block():
    out = compress_card_text(_CARD, 4)
    assert "示例" not in out
    # 保护块（代码）即使落在被丢弃的 section 内也保留
    assert 'print("keep me")' in out
    assert "知识正文" in out


def test_level5_summary_keeps_title_and_intro():
    out = compress_card_text(_CARD, 5)
    assert "标题" in out
    assert "开头导语" in out
    # 核心正文属于 ## 之后的一级段落 → 摘要模式丢弃（仅留标题+首段）
    assert "这段是真正" not in out
    # frontmatter 仍保留
    assert "anti_trigger" in out


def test_monotonic_length_non_increasing():
    lens = []
    for i in range(6):
        lens.append(len(compress_card_text(_CARD, i)))
    assert lens == sorted(lens, reverse=True)  # 每级不增长


def test_failure_falls_back_to_original():
    # 异常输入（如 None 由调用方守卫，这里模拟不可序列化路径）不抛错
    assert compress_card_text("", 5) == ""
    # 极端大 level 被钳制到 max_level，不越界
    assert compress_card_text(_CARD, 999) == compress_card_text(_CARD, 5)