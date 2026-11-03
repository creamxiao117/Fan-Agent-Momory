# @version V1.0 / 2026-11-02 / pi / evidence 轴（证据强度）单测
"""`infer_evidence`（A8 方案 A）单测：**只认结构标记**，不认散文措辞。

为何规则这么严（实测三版迭代）：
- v1（散文关键词）：一致率/精度差 —— 「引用别人的结论」「必须跑通（要求语气）」都会误判
- v2（结构标记）：仍会把「## 关键教训（适用所有 T1+ 任务）」这种**提及**误判成验证记录
- v3（最终）：T1 小节**且节内有实质证据**（结果形态/沙盒痕迹）⇒ 抽样目视 12/12 成立
"""

from common.frontmatter import EVIDENCE_VALUES, infer_evidence, validate_card


def test_t1_requires_real_proof_not_mention():
    """只**提及** T1（小节标题有 T1 但节内无证据）⇒ 不算 t1。"""
    body = "# 关键教训\n\n## 适用所有 T1+ 任务的通则\n\n本条适用于所有 T1 任务。\n"
    assert infer_evidence({}, body) == "none"


def test_t1_section_with_proof_counts():
    """T1 小节**且节内有实质证据**（结果形态/沙盒）⇒ t1。"""
    body = "# 卡\n\n## T1 迭代验证 — 2026-10-04\n\n沙盒 F:\\AgentMemoryT1\\x，exit 0。\n"
    assert infer_evidence({}, body) == "t1"


def test_explicit_frontmatter_evidence_t1_wins():
    """frontmatter 显式 `evidence: t1` ⇒ t1（人说了算，规则不覆盖）。"""
    assert infer_evidence({"evidence": "t1"}, "# 卡\n\n随便写点什么。\n") == "t1"


def test_measured_requires_result_shape():
    """measured 只认**结果形态**（tests pass / exit 码 / 负样本打红 / 实测次数…）。"""
    body = "# 卡\n\n## 验证\n\n298/298 tests pass，exit 0。\n"
    assert infer_evidence({}, body) == "measured"


def test_requirement_sentence_is_not_evidence():
    """「写完**必须**跑通再交付」= 规则陈述，**不是**验证记录。"""
    body = "# 卡\n\n## 规范\n\n写完必须跑通再交付，跑通时间不限。\n"
    assert infer_evidence({}, body) == "none"


def test_quoted_verified_is_not_evidence():
    """「引用别人的结论（已验证的事实）」不是自证 ⇒ none。"""
    body = "# 卡\n\n静态分析必须基于「已验证的事实」，不是「我以为的事实」。\n"
    assert infer_evidence({}, body) == "none"


def test_plain_card_is_none():
    assert infer_evidence({}, "# 随手记\n\n今天天气不错。\n") == "none"


def test_evidence_values_enum():
    assert set(EVIDENCE_VALUES) == {"none", "measured", "t1"}


def test_validate_card_rejects_bad_evidence():
    """evidence 取值非法 ⇒ 报错（但**缺失不报错**：可选字段，存量卡不带它）。"""
    from common.frontmatter import parse_card

    bad = parse_card("---\ntype: exp\ntags: [x]\nupdated: '2026-01-01'\nstatus: active\nevidence: guess\n---\n\n# x\n")
    assert any("evidence" in e for e in validate_card(bad))
    missing = parse_card("---\ntype: exp\ntags: [x]\nupdated: '2026-01-01'\nstatus: active\n---\n\n# x\n")
    assert not any("evidence" in e for e in validate_card(missing))


# ── 端到端：新卡入库自动带 evidence（ingest 路径）─────────────────────────


def _card(type_: str = "exp", body: str = "正文"):
    from common.frontmatter import parse_card

    return parse_card(
        "---\ntype: " + type_ + "\ntags: [pi]\nupdated: '2026-11-02'\nstatus: candidate\n---\n\n" + body + "\n"
    )


def _draft(root, name, card):
    from common.frontmatter import write_card

    d = root / ".sync" / "drafts" / "pi_draft"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(write_card(card), encoding="utf-8")
    return p


def test_promote_fills_evidence_for_new_card(tmp_path):
    """新卡落权威区时**自动补** evidence（只填新卡，不改 grade、不改存量）。"""
    from common.frontmatter import parse_card
    from sync import _promote_or_conflict_draft

    root = tmp_path / "hub"
    (root / "blueprints").mkdir(parents=True)
    body = "# 蓝图\n\n## T1 验证 — 2026-11-01\n\n沙盒 F:\\AgentMemoryT1\\x，exit 0。\n"
    card = _card(type_="blueprint", body=body)
    p = _draft(root, "b1.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _promote_or_conflict_draft(root, "pi", p, card, stat)

    got = parse_card((root / "blueprints" / "b1.md").read_text(encoding="utf-8"))
    assert got.extra.get("evidence") == "t1"
    assert got.extra.get("grade"), "grade 仍按目录默认值补齐（不受 evidence 影响）"


def test_promote_does_not_override_existing_evidence(tmp_path):
    """卡已声明 evidence 时不得被覆盖（尊重作者显式取值）。"""
    from common.frontmatter import parse_card
    from sync import _promote_or_conflict_draft

    root = tmp_path / "hub"
    (root / "blueprints").mkdir(parents=True)
    card = _card(type_="blueprint", body="# 卡\n\n## T1 验证\n\n沙盒 exit 0。\n")
    card.extra["evidence"] = "none"
    p = _draft(root, "b2.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _promote_or_conflict_draft(root, "pi", p, card, stat)

    got = parse_card((root / "blueprints" / "b2.md").read_text(encoding="utf-8"))
    assert got.extra.get("evidence") == "none", "显式声明的 evidence 不得被推断覆盖"
