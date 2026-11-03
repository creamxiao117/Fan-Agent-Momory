# @version V1.0 / 2026-11-03 / pi / MCP Apps 人类卡片渲染（A+ 方案）
"""`ui://agent-memory-hub/<tool>.html` 的人类可读卡片。

要点
----
1. 卡片必须**回答人真正会问的四件事**：做什么 / 怎么调 / 返回什么 / 中枢里现在有什么；
2. 参数表**由 inputSchema 自动生成** ⇒ 不会与实现漂移；
3. **明示「这是给人类看的」** ⇒ 避免以后有人误以为 agent 需要这个界面；
4. 渲染失败**降级不抛**（绝不阻断宿主的工具调用）。
"""

import re

from tools.mcp_handlers import PARAM_DOCS, render_error_card, render_tool_card


def _text(html: str) -> str:
    h = re.sub(r"(?s)<style.*?</style>", " ", html)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def test_card_answers_the_four_questions(tmp_path):
    html = render_tool_card(
        tmp_path,
        "hub_search",
        "混合检索中枢",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    )
    txt = _text(html)
    assert "它做什么" in txt
    assert "边界" in txt
    assert "返回" in txt
    assert "参数" in txt
    assert "中枢现状" in txt
    assert "query" in txt and "检索词" in txt  # 参数表带人话说明


def test_card_states_it_is_for_humans(tmp_path):
    """卡片必须**明示给人类**（Agent 走文本响应）——避免以后误以为 agent 需要界面。"""
    txt = _text(render_tool_card(tmp_path, "hub_get", "读单卡", {}))
    assert "人类" in txt
    assert "Agent" in txt


def test_card_is_valid_html_ish(tmp_path):
    html = render_tool_card(tmp_path, "hub_index", "浏览目录", {})
    assert html.lstrip().startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in html
    assert html.rstrip().endswith("</html>")


def test_card_escapes_untrusted_text(tmp_path):
    """卡标题/描述来自代码常量，但**仍要转义**（将来若改成动态来源，别引入注入）。"""
    html = render_tool_card(tmp_path, "x", "<script>alert(1)</script>", {})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_param_docs_cover_common_params():
    for p in ("query", "top_k", "mode", "include_body", "compress_level", "platform", "id", "type", "tags"):
        assert p in PARAM_DOCS, f"参数 {p} 缺少人话说明"


def test_error_card_degrades_gracefully():
    html = render_error_card("hub_search", "boom")
    assert "降级" in _text(html)
    assert "文本响应" in _text(html)
