from pathlib import Path

from common.frontmatter import parse_card, write_card
from scripts.bootstrap_hub import bootstrap
from sync import append_log, confirm_rule, ingest


# 2026-09-02 权威区收缩适配：低风险自动入区类型改用 longterm（exp 不再进权威区）
def _make_draft(
    root: Path, platform: str, name: str, body: str, ctype: str = "longterm"
) -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    card = parse_card(f"""---
type: {ctype}
tags:
  - test
updated: 2026-08-17
status: candidate
reuse_count: 0
---
{body}
""")
    p = d / name
    p.write_text(write_card(card), encoding="utf-8")
    return p


def test_ingest_promotes_low_risk_to_authority(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="longterm")
    stat = ingest(root, "trae")
    assert stat["promoted"] == 1
    assert (root / "longterm" / "exp-a.md").exists()
    assert stat["status"] == "ok"


def test_ingest_rule_goes_to_pending_not_authority(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "rule-x.md", "重要硬约束：DLL 必须递增版本", ctype="rule")
    stat = ingest(root, "trae")
    assert stat["pending"] == 1
    assert not (root / "rules" / "rule-x.md").exists()
    assert (root / ".sync" / "pending" / "rule-x.md").exists()


def test_ingest_duplicate_goes_to_conflicts(tmp_path):
    root = bootstrap(tmp_path)
    (root / "longterm" / "exp-a.md").write_text(
        "---\ntype: longterm\ntags: [test]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n这是一条经验卡片内容\n",
        encoding="utf-8",
    )
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="longterm")
    stat = ingest(root, "trae")
    assert stat["duplicate"] == 1
    assert list((root / ".sync" / "conflicts").glob("*.md"))


def test_ingest_duplicate_deletes_draft(tmp_path):
    """重复草稿处理后必须删除，避免下次同步重复处理并覆盖冲突区"""
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="longterm")
    ingest(root, "trae")
    # 再次写入完全一致的内容 → 判为重复进冲突区，且草稿被删除
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="longterm")
    stat = ingest(root, "trae")
    assert stat["duplicate"] == 1
    assert not (root / ".sync" / "drafts" / "trae_draft" / "exp-a.md").exists()


def test_ingest_same_name_different_content_no_overwrite(tmp_path):
    """同名不同内容（语义不重复）→ 不得覆盖权威区，转冲突区且删除草稿"""
    root = bootstrap(tmp_path)
    (root / "longterm" / "exp-a.md").write_text(
        "---\ntype: longterm\ntags: [test]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n记录一次排查 Windows 系统崩溃的经验\n",
        encoding="utf-8",
    )
    _make_draft(root, "trae", "exp-a.md", "如何制作拿铁咖啡的心得体会", ctype="longterm")
    stat = ingest(root, "trae")
    # 权威区内容保持不变（未被草稿覆盖）
    assert "排查 Windows 系统崩溃" in (root / "longterm" / "exp-a.md").read_text(
        encoding="utf-8"
    )
    # 同名不同内容计入冲突，草稿被删除
    assert stat["duplicate"] == 1
    assert not (root / ".sync" / "drafts" / "trae_draft" / "exp-a.md").exists()


def test_confirm_rule_promotes_to_rules(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "rule-x.md", "重要硬约束：DLL 必须递增版本", ctype="rule")
    ingest(root, "trae")
    dst = confirm_rule(root, "rule-x.md")
    assert dst.exists()
    assert dst.parent.name == "rules"


def test_confirm_methodology_routes_by_type(tmp_path):
    """methodology 类型待确认卡 → confirm 后应落 methodology/ 而非硬编码 rules/"""
    root = bootstrap(tmp_path)
    _make_draft(
        root,
        "trae",
        "meth-y.md",
        "收尾建议清单方法论：任务完成后的结构化待办",
        ctype="methodology",
    )
    stat = ingest(root, "trae")
    assert stat["pending"] == 1  # 高风险类型（rule+methodology）进 pending
    assert (root / ".sync" / "pending" / "meth-y.md").exists()
    dst = confirm_rule(root, "meth-y.md")
    assert dst.exists()
    assert dst.parent.name == "methodology"  # 路由到类型对应权威区
    assert not (root / "rules" / "meth-y.md").exists()  # 不得再进 rules
    card = parse_card(dst.read_text(encoding="utf-8"))
    assert card.status == "active"


def test_confirm_bare_name_without_md_suffix(tmp_path):
    """CLI 传裸卡名（不含 .md）→ 自动补后缀可确认（此前必报 FileNotFoundError）"""
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "rule-z.md", "重要硬约束：发布前必须过门禁", ctype="rule")
    ingest(root, "trae")
    dst = confirm_rule(root, "rule-z")  # 裸名，不带 .md
    assert dst.exists()
    assert dst.name == "rule-z.md"


def test_append_log_uses_unified_prefix(tmp_path):
    root = bootstrap(tmp_path)
    append_log(root, "ingest", "测试写入")
    lines = (root / "retro" / "log.md").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("## [") and "| 测试写入" in line for line in lines)


def test_ingest_writes_memory_diff(tmp_path):
    """ingest 写回路径同步产结构化变更审计（OpenViking 路径 C 落地）"""
    from tools.memory_diff import read_records

    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="longterm")
    ingest(root, "trae")
    recs = read_records(root)
    assert any(
        r.get("op") == "add"
        and r.get("name") == "exp-a.md"
        and r.get("after") == "longterm/exp-a.md"
        for r in recs
    )


def test_ingest_exp_draft_moves_to_experience_not_deleted(tmp_path):
    """2026-09-02 用户指令：非权威区 type(exp/note/retro) 草稿 ingest 时
    改挪 experience/ 而非删除——经验层内容留档备查，不参与权威区检索。"""
    from tools.memory_diff import read_records

    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-b.md", "这是一条待留档的经验记录", ctype="exp")
    stat = ingest(root, "trae")
    assert stat["moved"] == 1  # 计数：改挪 1 张
    assert (root / "experience" / "exp-b.md").exists()  # 内容被保留
    # 草稿已移走（不再出现在草稿区）
    assert not (root / ".sync" / "drafts" / "trae_draft" / "exp-b.md").exists()
    recs = read_records(root)
    assert any(
        r.get("op") == "move"
        and r.get("name") == "exp-b.md"
        and r.get("after") == "experience/exp-b.md"
        for r in recs
    )


def test_ingest_exp_draft_same_name_keeps_both(tmp_path):
    """同名词防覆盖：experience/ 已有同名卡时追加时间戳后缀，不互相覆盖"""
    root = bootstrap(tmp_path)
    (root / "experience").mkdir(parents=True, exist_ok=True)
    (root / "experience" / "exp-b.md").write_text("旧经验\n", encoding="utf-8")
    _make_draft(root, "trae", "exp-b.md", "新经验内容", ctype="exp")
    stat = ingest(root, "trae")
    assert stat["moved"] == 1
    # 旧卡未被覆盖（内容仍为"旧经验"），新卡带后缀落盘
    assert "旧经验" in (root / "experience" / "exp-b.md").read_text(encoding="utf-8")
    preserved = [p for p in (root / "experience").glob("exp-b-*.md")]
    assert len(preserved) == 1
    assert "新经验内容" in preserved[0].read_text(encoding="utf-8")
