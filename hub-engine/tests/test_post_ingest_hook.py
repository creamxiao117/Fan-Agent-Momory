"""post_ingest_hook.extract_summary 单测：样板标题不得被当摘要返回。

背景：卡片按写作规范以 `# 结论先行` / `# 一句话结论` 作为 H1，旧实现直接返回该
标题 → INDEX 描述退化成 4 字符「结论先行」，触发 audit「描述过短」告警。
"""

from pathlib import Path

from scripts.post_ingest_hook import extract_summary


def _card(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: exp\ntags:\n- a\n---\n\n{body}", encoding="utf-8")
    return p


def test_boilerplate_heading_falls_through_to_paragraph(tmp_path):
    p = _card(tmp_path / "a.md", "# 结论先行\n\n把域名强制 DIRECT 会导致登录失败。\n")
    got = extract_summary(p)
    assert got == "把域名强制 DIRECT 会导致登录失败。"
    assert len(got) > 4


def test_one_line_conclusion_boilerplate_skipped(tmp_path):
    p = _card(tmp_path / "b.md", "# 一句话结论\n\nX 与 Y 的因果关系。\n")
    assert extract_summary(p) == "X 与 Y 的因果关系。"


def test_real_h1_title_is_returned(tmp_path):
    p = _card(tmp_path / "c.md", "# PluginHub 注册卡：speech_input\n\n正文段落\n")
    assert extract_summary(p) == "PluginHub 注册卡：speech_input"


def test_h2_skipped_then_paragraph(tmp_path):
    p = _card(tmp_path / "d.md", "## 小标题\n\n段落文本。\n")
    assert extract_summary(p) == "段落文本。"


def test_missing_file_returns_empty(tmp_path):
    assert extract_summary(tmp_path / "nope.md") == ""
