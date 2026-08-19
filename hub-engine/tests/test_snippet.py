"""snippet 节选单测：抽取正文中与查询最相关的片段（不依赖检索/模型）"""

from tools.snippet import extract_snippet

BODY = """# 规则标题
这是第一段引言，没有任何检索关键词。
关键规则：修改 DLL 后必须递增版本号，避免被 AutoCAD 占用锁住源文件。
第三段补充：容量锁定与备份策略。
"""


def test_picks_keyword_line_not_first():
    """query 命中第二行，应优先返回该行（含上下文），而非第一行标题。"""
    seg = extract_snippet(BODY, "DLL 递增版本号")
    assert "递增版本号" in seg
    assert seg.index("递增版本号") < seg.index("第三段")


def test_empty_query_falls_back_to_head():
    assert extract_snippet(BODY, "") == BODY[:200]


def test_no_keyword_hit_falls_back_to_head():
    """无命中词时回退取正文开头，行为不劣于旧 excerpt。"""
    seg = extract_snippet(BODY, "火星探测器")  # 无命中
    assert seg.startswith(BODY[:20])


def test_english_word_hit():
    seg = extract_snippet(BODY, "autocad locking")
    assert "AutoCAD" in seg


def test_long_truncates():
    # 每行足够长，使命中的 3 行片段 > 200 → 触发截断加省略号，但仍含命中行
    long_body = "\n".join(f"行{i} " + "内容填充" * 40 for i in range(30))
    seg = extract_snippet(long_body, "行15")
    assert len(seg) <= 200
    assert seg.endswith("…")
    assert "行15" in seg
