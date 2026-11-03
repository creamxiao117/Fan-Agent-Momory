# @version V1.0 / 2026-11-02 / pi / evidence 轴落到检索侧（摘要长度加成 + 透出 + 注入标记）
"""A8 方案 A 的「检索侧」用法（2026-11-02）。

要点：`grade` 是混合轴 ⇒ **「随手记的教训」与「已验证的教训」都落 task 档** ⇒
两者摘录长度相同（140）⇒ **已验证的内容被压成一行，等于白验证**。

⇒ 三处落地：
1. **摘要长度加成**：`EXCERPT_BY_GRADE[grade] + EXCERPT_BY_EVIDENCE[evidence]`
   （task+measured = 240 ≈ proven；iron+t1 = 550，仍在注入预算内）
2. **透出 evidence**：命中项带 `evidence` 字段 ⇒ 消费方可据此判断可信度
3. **注入标记**：注入块行首标 `[grade][evidence]` ⇒ 「已验证的教训」一眼可辨
"""

from tools.mcp_handlers import EXCERPT_BY_EVIDENCE, EXCERPT_BY_GRADE, _hit


def _card(tmp_path, *, grade="task", evidence="", body="正文内容"):
    from common.frontmatter import parse_card

    fm = ["---", "type: exp", "tags: [x]", "updated: '2026-11-02'", "status: active"]
    if grade:
        fm.append(f"grade: {grade}")
    if evidence:
        fm.append(f"evidence: {evidence}")
    p = tmp_path / "experience" / "c.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    card = parse_card("\n".join(fm) + "\n---\n\n" + body + "\n")
    card.path = p
    return card


def test_excerpt_length_gets_evidence_bonus(tmp_path):
    """带实测证据的 task 卡 ⇒ 摘录比同 grade 无证据的卡**更长**。"""
    body = "标题\n\n" + ("验证段内容。" * 80)
    a = _hit(_card(tmp_path / "a", grade="task", evidence="", body=body), "word", 1.0, tmp_path, False, "验证段")
    b = _hit(
        _card(tmp_path / "b", grade="task", evidence="measured", body=body), "word", 1.0, tmp_path, False, "验证段"
    )
    assert len(b["excerpt"]) > len(a["excerpt"])


def test_evidence_is_exposed_in_hit(tmp_path):
    """命中项透出 evidence（消费方据此判断可信度）。"""
    h = _hit(_card(tmp_path, grade="task", evidence="t1"), "word", 1.0, tmp_path, False, "x")
    assert h["evidence"] == "t1"
    assert h["grade"] == "task"


def test_evidence_bonus_table_is_bounded():
    """加成表有界（防止把注入块撑爆）。"""
    assert set(EXCERPT_BY_EVIDENCE) == {"t1", "measured"}
    for v in EXCERPT_BY_EVIDENCE.values():
        assert 0 < v <= 200, v
    # 最坏情况：iron + t1
    worst = EXCERPT_BY_GRADE["iron"] + EXCERPT_BY_EVIDENCE["t1"]
    assert worst <= 600, f"最坏摘录 {worst} 过长"
