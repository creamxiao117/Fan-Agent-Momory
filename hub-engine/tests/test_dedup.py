"""OpenViking 路径 B 落地测试：向量预过滤 + LLM 去重决策（dedup.py + sync ingest 接入）"""

from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from sync import ingest
from tools.dedup import candidates, parse_decision


def _seed_authority(root: Path, name: str, body: str, ctype: str = "exp") -> None:
    """在权威区预置一张同主题卡，作为去重候选"""
    (root / "experience").mkdir(parents=True, exist_ok=True)
    (root / "experience" / name).write_text(
        f"---\ntype: {ctype}\ntags: [test]\nupdated: 2026-08-17\nstatus: active\n"
        f"reuse_count: 0\n---\n{body}\n",
        encoding="utf-8",
    )


def _make_draft(
    root: Path, platform: str, name: str, body: str, ctype: str = "exp"
) -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(
        f"---\ntype: {ctype}\ntags: [test]\nupdated: 2026-08-17\nstatus: candidate\n"
        f"reuse_count: 0\n---\n{body}\n",
        encoding="utf-8",
    )
    return d / name


# ---------- tools/dedup 单元 ----------


def test_parse_decision_valid():
    d = parse_decision(
        '{"action":"merge","target":"a.md","reason":"同主题互补","confidence":0.9}'
    )
    assert d["action"] == "merge"
    assert d["target"] == "a.md"
    assert d["confidence"] == 0.9


def test_parse_decision_invalid_action_defaults_review():
    d = parse_decision('{"action":"rm-rf","target":"a.md"}')
    assert d["action"] == "review"


def test_parse_decision_nonjson_defaults_review():
    d = parse_decision("呃，这个不好说")
    assert d["action"] == "review"


def test_parse_decision_lowercases_and_bounds(tmp_path):
    d = parse_decision('{"action":" SKIP ","target":null,"confidence":1.7}')
    assert d["action"] == "skip"
    assert d["confidence"] == 1.0


# ---------- tools/dedup candidates ----------


def test_candidates_prefilter_similar(tmp_path):
    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "这是一条在线支付接入的经验卡片")
    _make_draft(root, "trae", "new.md", "这是一条在线支付接入的经验卡片")
    card = __import__("common.frontmatter", fromlist=["try_read_card"]).try_read_card(
        Path(root) / ".sync" / "drafts" / "trae_draft" / "new.md"
    )
    hits = candidates(root, card)
    assert hits, "同主题卡应被向量预过滤命中"
    assert hits[0][0].path.name == "exp-a.md"


def test_candidates_no_match(tmp_path):
    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "拍奶泡咖啡的经验")
    _make_draft(root, "trae", "new.md", "PS5 手柄电池更换步骤")
    card = __import__("common.frontmatter", fromlist=["try_read_card"]).try_read_card(
        Path(root) / ".sync" / "drafts" / "trae_draft" / "new.md"
    )
    assert candidates(root, card) == []


# ---------- sync ingest 接入 ----------


def test_ingest_default_no_llm_goes_to_conflicts(tmp_path):
    """chat_fn 缺省（离线/无 LLM）→ 走 legacy 纯向量去重，冲突区人工"""
    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    _make_draft(root, "trae", "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    stat = ingest(root, "trae")
    assert stat["duplicate"] == 1
    assert list((root / ".sync" / "conflicts").glob("trae_exp-a.md"))


def test_ingest_llm_skip_highconf_drops_draft(tmp_path):
    """LLM 高置信 skip → 丢弃草稿，不进冲突区"""

    def _chat(_prompt, _root):
        return '{"action":"skip","target":"exp-a.md","reason":"完全重复","confidence":0.95}'

    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    d = _make_draft(root, "trae", "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    stat = ingest(root, "trae", chat_fn=_chat)
    assert stat["duplicate"] == 1
    assert not d.exists(), "高置信 skip 应丢弃草稿"
    assert not list((root / ".sync" / "conflicts").glob("*.md")), "不应落冲突区"


def test_ingest_llm_merge_still_goes_to_conflicts(tmp_path):
    """LLM merge 建议 → 仍进冲突区人工终审，附 .pred.json，不自动合并"""
    from tools.memory_diff import read_records

    def _chat(_prompt, _root):
        return '{"action":"merge","target":"exp-a.md","reason":"建议合并","confidence":0.6}'

    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "在线支付时序分析的常规做法")
    _make_draft(root, "trae", "exp-b.md", "在线支付时序分析的进阶技巧补充")
    stat = ingest(root, "trae", chat_fn=_chat)
    assert stat["duplicate"] == 1
    preds = list((root / ".sync" / "conflicts").glob("*.pred.json"))
    assert preds, "merge 建议应落地 .pred.json 伴生文件"
    import json

    dec = json.loads(preds[0].read_text(encoding="utf-8"))["decision"]
    assert dec["action"] == "merge"
    # 权威区未被自动合并覆盖
    assert (root / "experience" / "exp-a.md").exists()
    # 审计留痕
    recs = read_records(root)
    assert any(r.get("op") == "delete" for r in recs)


def test_ingest_llm_invalid_decision_falls_back_to_conflicts(tmp_path):
    """LLM 输出非法 → 降级 review，仍进冲突区人工（不误删）"""

    def _chat(_prompt, _root):
        return "看不懂"

    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    _make_draft(root, "trae", "exp-b.md", "这是一条在线支付日志解析的经验卡片")
    stat = ingest(root, "trae", chat_fn=_chat)
    assert stat["duplicate"] == 1
    # 权威区原卡仍在（未误删）
    assert (root / "experience" / "exp-a.md").exists()
    assert list((root / ".sync" / "conflicts").glob("trae_exp-b.md"))


def test_ingest_no_candidate_promotes(tmp_path):
    """无相似候选 → 正常提升，不被 LLM 误判"""
    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "拍奶泡咖啡的经验")
    _make_draft(root, "trae", "exp-c.md", "PS5 手柄电池更换步骤")
    stat = ingest(root, "trae")
    assert stat["promoted"] == 1
    assert (root / "experience" / "exp-c.md").exists()


def test_ingest_llm_create_highconf_auto_promotes(tmp_path):
    """反哺(2026-08-21)：LLM 高置信 create（新卡、与候选主题不同）→ 自动入区，不落冲突区"""

    def _chat(_prompt, _root):
        return '{"action":"create","target":null,"reason":"主题不同无重复","confidence":0.92}'

    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "这是一条在线支付日志解析的经验卡片")
    _make_draft(root, "trae", "exp-b.md", "这是一条治腰痛的经验卡片")
    stat = ingest(root, "trae", chat_fn=_chat)
    assert stat["promoted"] == 1, stat
    assert (root / "experience" / "exp-b.md").exists()
    assert not list((root / ".sync" / "conflicts").glob("*.md")), (
        "高置信 create 不应落冲突区"
    )


def test_ingest_llm_create_highconf_same_name_still_conflicts(tmp_path):
    """反哺安全兜底：LLM 高置信 create 但权威区同名不同内容 → 仍落冲突区，不覆盖"""

    def _chat(_prompt, _root):
        return '{"action":"create","target":null,"reason":"主题不同无重复","confidence":0.92}'

    root = bootstrap(tmp_path)
    _seed_authority(root, "exp-a.md", "在线支付时序分析的常规做法")
    _make_draft(root, "trae", "exp-a.md", "在线支付时序分析的进阶技巧补充")
    stat = ingest(root, "trae", chat_fn=_chat)
    assert stat["duplicate"] == 1, stat
    assert list((root / ".sync" / "conflicts").glob("trae_exp-a.md")), "同名应进冲突区"
    # 权威区原卡未被覆盖
    body = (root / "experience" / "exp-a.md").read_text(encoding="utf-8")
    assert "常规做法" in body
