# @version V1.0 / 2026-09-23 / pi / audit_index 单测（重点：misrouted_entry 错位登记维度）

"""`audit_index` 单测。

## 为什么要测这个新维度
A4 把 experience 整区从根 INDEX 拆到 `INDEX-experience.md`（根 INDEX 只留指针）后，
两个写入方（`post_ingest_hook` / `fix_orphans`）没跟着改，继续把经验卡追加回根 INDEX：
- **白涨 L0 预算**（拆分本就是为了压 L0）
- 分册失去意义

而 audit 原有的 orphan/ghost/格式/重复四个维度**都查不出**这种错位——
是人工跑 ingest 时才偶然撞见的。`misrouted_entry` 维度即把"人工撞见"变成"门禁自动发现"。
"""

from pathlib import Path

from scripts.audit_index import INDEX_FILES_AUDITED, audit
from scripts.bootstrap_hub import bootstrap


def _hub(tmp_path: Path, root_index_extra: str = "") -> Path:
    """最小中枢：根 INDEX（rules 区 + experience 指针区）+ 分册"""
    root = bootstrap(tmp_path)
    (root / "rules" / "alpha.md").write_text(
        "---\ntype: rule\ntags:\n- a\nupdated: 2026-09-23\nstatus: active\n---\n\n# Alpha 规则\n",
        encoding="utf-8",
    )
    (root / "INDEX.md").write_text(
        "## 规则（rules/）\n"
        "- alpha    Alpha 规则\n"
        "\n"
        "## 经验（experience/）\n"
        "详见 INDEX-experience.md（L2 按需）；experience/ 目录按需检索。\n"
        f"{root_index_extra}",
        encoding="utf-8",
    )
    (root / "INDEX-experience.md").write_text(
        "# 中枢索引 · 经验分册（INDEX-experience，L2 按需）\n\n## 经验（experience/）\n",
        encoding="utf-8",
    )
    return root


def _types(result: dict) -> list[str]:
    return [i["type"] for i in result["issues"]]


def test_audits_both_index_files():
    """两个 INDEX 文件都必须被审计（此前只审根 INDEX，分册 216 条无人看管）"""
    assert INDEX_FILES_AUDITED == ("INDEX.md", "INDEX-experience.md")


def test_clean_hub_has_no_misrouted_issue(tmp_path):
    """正确登记（experience 只留指针）→ 不得报错位"""
    result = audit(_hub(tmp_path))
    assert "misrouted_entry" not in _types(result), result["issues"]


def test_detects_experience_entry_in_root_index(tmp_path):
    """**核心回归**：根 INDEX 的经验区里出现卡条目 → 必须报 misrouted_entry（high）

    这正是 2026-09-23 实际发生的 bug：写入方把经验卡追加回根 INDEX。
    """
    root = _hub(tmp_path, root_index_extra="- fake-card    误入根 INDEX 的经验条目\n")
    result = audit(root)
    hits = [i for i in result["issues"] if i["type"] == "misrouted_entry"]
    assert hits, f"应报错位登记，实际: {_types(result)}"
    it = hits[0]
    assert it["slug"] == "fake-card"
    assert it["in_file"] == "INDEX.md"
    assert it["expected_file"] == "INDEX-experience.md"
    assert it["severity"] == "high", "错位会导致 L0 回涨，应为 high"


def test_detects_authority_section_inside_experience_file(tmp_path):
    """反向错位：**分册里出现非经验分区**（如 `## 规则（rules/）`）→ 报错位到根 INDEX。

    注：判据是「**按分区**」而非「按卡」——把一张 rules 卡写在分册的经验区里，
    分区仍是 experience，仍算位置正确（卡与分区不一致的问题由 orphan/ghost 维度管）。
    """
    root = _hub(tmp_path)
    (root / "INDEX-experience.md").write_text(
        "# 分册\n\n## 经验（experience/）\n\n## 规则（rules/）\n- beta    Beta 规则\n",
        encoding="utf-8",
    )
    hits = [i for i in audit(root)["issues"] if i["type"] == "misrouted_entry"]
    assert hits, "分册里的 rules 分区条目应被报错位"
    assert hits[0]["in_file"] == "INDEX-experience.md"
    assert hits[0]["expected_file"] == "INDEX.md"


def test_prose_sections_are_not_flagged(tmp_path):
    """说明性分区（使用约定/沉淀通道）不是卡片清单分区 → 不得误报"""
    root = _hub(tmp_path)
    text = (root / "INDEX.md").read_text(encoding="utf-8")
    (root / "INDEX.md").write_text(
        text + "\n## 沉淀通道\n- 某说明文字    这不是卡登记\n", encoding="utf-8"
    )
    assert "misrouted_entry" not in _types(audit(root))
