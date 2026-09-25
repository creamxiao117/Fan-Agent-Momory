# @version V1.0 / 2026-09-23 / pi / INDEX 摘要质量测试：边界断句 / BOM 容错 / 卡摘要重建

"""INDEX 摘要质量（2026-09-23）。

背景：A4 用 `slim_index --max-desc 10` 机械字符截断，INDEX 里 239/251 条变成
读不懂的半截词（`GitHub 仓库选…`）——省了字符却丢了信息。现改为用卡自身摘要
（`extract_summary`）+ 子句边界断句，本文件锁住这些行为。
"""

from pathlib import Path

from scripts.post_ingest_hook import cut_at_boundary, extract_summary
from scripts.regen_index_desc import _build_card_index, regen_text


def _card(p: Path, body: str, bom: bool = False) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\ntype: exp\ntags:\n- a\nupdated: 2026-09-23\nstatus: active\n---\n\n{body}"
    p.write_text(("\ufeff" if bom else "") + text, encoding="utf-8")
    return p


# ---------------------------------------------------------------- 边界断句


def test_cut_at_boundary_breaks_on_clause_not_midword():
    """超长描述必须在子句边界断开，不能切出半截词"""
    text = "第一句话讲清楚了。第二句话也很重要但是会被截掉"
    got = cut_at_boundary(text, 12)
    assert got == "第一句话讲清楚了。", f"应在句号处断句，实际: {got!r}"
    assert "…" not in got, "在自然边界断句时不应补省略号"


def test_cut_at_boundary_appends_ellipsis_only_when_hard_cut():
    """无边界可断时才补省略号（明确表示被截断）"""
    got = cut_at_boundary("abcdefghijklmnop", 8)
    assert got.endswith("…")
    assert len(got) <= 8


def test_cut_at_boundary_returns_short_text_unchanged():
    assert cut_at_boundary("短描述", 40) == "短描述"
    assert cut_at_boundary("", 40) == ""


# ---------------------------------------------------------------- extract_summary


def test_extract_summary_handles_bom(tmp_path):
    """带 BOM 的卡必须仍能取到摘要（回归：旧实现用 utf-8 读取，
    `\\ufeff---` 使 frontmatter 判定失败 → 整个函数返回空 →
    实测 19/655 个 .md 因此在 INDEX 无描述）"""
    p = _card(tmp_path / "bommed.md", "# 正常标题\n\n正文第一段。\n", bom=True)
    got = extract_summary(p)
    assert got == "正常标题", f"带 BOM 的卡应能取到摘要，实际: {got!r}"
    assert got != "", "BOM 不应导致空摘要"


def test_extract_summary_without_bom_unchanged(tmp_path):
    """无 BOM 的卡行为不变（防修 BOM 时误伤）"""
    p = _card(tmp_path / "plain.md", "# 正常标题\n\n正文第一段。\n")
    assert extract_summary(p) == "正常标题"


def test_extract_summary_skips_boilerplate_and_uses_conclusion_body(tmp_path):
    """样板标题（一句话结论等）不是摘要 → 取其下的正文段落"""
    p = _card(
        tmp_path / "concl.md",
        "## 一句话结论\n\n乱码不是语言问题，是链路上某一环不一致。\n",
    )
    assert extract_summary(p) == "乱码不是语言问题，是链路上某一环不一致。"


def test_extract_summary_preserves_underscores_in_identifiers(tmp_path):
    """下划线不是 markdown 强调符，不得删（回归：旧实现删 `_` 使
    `speech_input` 变成 `speechinput`）"""
    p = _card(tmp_path / "id.md", "# PluginHub 注册卡：speech_input\n")
    assert extract_summary(p) == "PluginHub 注册卡：speech_input"


def test_extract_summary_skips_table_and_code_lines(tmp_path):
    """首行是表格/代码围栏时不当作摘要（否则会取到 `|` 或 ``` 垃圾）"""
    p = _card(tmp_path / "tbl.md", "| a | b |\n|---|---|\n| 1 | 2 |\n\n真正的结论段落。\n")
    assert extract_summary(p) == "真正的结论段落。"


def test_extract_summary_respects_max_len(tmp_path):
    p = _card(tmp_path / "long.md", "# 标题\n\n" + "一" * 100 + "。后续内容\n")
    got = extract_summary(p, max_len=40)
    assert len(got) <= 40, f"应受 max_len 约束，实际 {len(got)}"


# ---------------------------------------------------------------- regen_index_desc


def test_regen_rewrites_resolvable_cards_and_keeps_legend(tmp_path):
    """能解析到卡的条目被重建；目录图例行/笔记行原样保留"""
    hub = tmp_path / "hub"
    _card(hub / "experience" / "my-card.md", "# 我的卡片标题\n")
    cards = _build_card_index(hub)
    assert "my-card" in cards

    text = (
        "## 经验（experience/）\n"
        "- experience/    经验（踩坑/排障/实测结论）\n"
        "- my-card    旧的被截断描述…\n"
        "- 不是卡的条目    这行不能被改\n"
    )
    new, stats = regen_text(text, cards, max_desc=40)
    assert "旧的被截断描述" not in new
    assert "- my-card    我的卡片标题" in new
    assert "- experience/    经验（踩坑/排障/实测结论）" in new, "图例行不得改动"
    assert "- 不是卡的条目    这行不能被改" in new, "无法解析的条目不得改动"
    assert stats["rewritten"] == ["my-card"]
    assert "不是卡的条目" in stats["unresolved"]


def test_regen_is_idempotent(tmp_path):
    """重跑不应产生变化（幂等）"""
    hub = tmp_path / "hub"
    _card(hub / "rules" / "c.md", "# 卡片标题\n")
    cards = _build_card_index(hub)
    text = "- c    旧描述\n"
    once, _ = regen_text(text, cards, max_desc=40)
    twice, stats2 = regen_text(once, cards, max_desc=40)
    assert once == twice
    assert stats2["unchanged"] == ["c"]
    assert stats2["rewritten"] == []


def test_regen_leaves_line_when_summary_empty(tmp_path):
    """卡存在但取不到摘要 → 不写空描述（保留原行，避免把描述清空）"""
    hub = tmp_path / "hub"
    p = hub / "rules" / "empty.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntype: rule\ntags:\n- a\nupdated: 2026-09-23\nstatus: active\n---\n",
        encoding="utf-8",
    )
    cards = _build_card_index(hub)
    text = "- empty    原有描述\n"
    new, stats = regen_text(text, cards, max_desc=40)
    assert new == text, "取不到摘要时不得清空描述"
    assert stats["empty_summary"] == ["empty"]
