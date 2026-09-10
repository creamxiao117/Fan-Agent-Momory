"""fix_index_registry 单测：幽灵 slug 纠偏（title / 日期前缀）、护栏、散文行不误报"""

from pathlib import Path

from scripts.fix_index_registry import apply_ghost_fixes, scan


def _card(p: Path, front: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{front}\n---\n\n正文\n", encoding="utf-8")


def _index(root: Path, text: str) -> None:
    (root / "INDEX.md").write_text(text, encoding="utf-8")


def test_ghost_fixed_via_frontmatter_title(tmp_path):
    """INDEX 按卡 title 登记、文件名不同 → 应纠偏到文件名 stem（2026-09-10 真实案例）"""
    _card(
        tmp_path / "methodology" / "2026-09-10-refactor-judgment-fanout-not-loc.md",
        "type: methodology\ntags: [x]\nupdated: '2026-09-10'\nstatus: active\n"
        "reuse_count: 0\ntitle: refactor-judgment-fanout-and-testability-not-loc",
    )
    _index(
        tmp_path,
        "## 方法论（methodology/）\n- refactor-judgment-fanout-and-testability-not-loc    描述文本\n",
    )
    res = scan(tmp_path)
    assert res["ghost_fixable"] == [
        (
            2,
            "refactor-judgment-fanout-and-testability-not-loc",
            "2026-09-10-refactor-judgment-fanout-not-loc",
        )
    ]
    assert apply_ghost_fixes(tmp_path, res["ghost_fixable"]) == 1
    assert "- 2026-09-10-refactor-judgment-fanout-not-loc" in (
        tmp_path / "INDEX.md"
    ).read_text(encoding="utf-8")


def test_ghost_fixed_via_date_prefix(tmp_path):
    _card(
        tmp_path / "methodology" / "2026-08-17-old-project-minimal-migration.md",
        "type: methodology\ntags: [x]\nupdated: '2026-08-17'\nstatus: active\nreuse_count: 0",
    )
    _index(
        tmp_path,
        "## 方法论（methodology/）\n- old-project-minimal-migration    描述文本\n",
    )
    res = scan(tmp_path)
    assert [(s, n) for _, s, n in res["ghost_fixable"]] == [
        ("old-project-minimal-migration", "2026-08-17-old-project-minimal-migration")
    ]


def test_candidate_already_registered_is_manual(tmp_path):
    """候选 stem 已被登记 → 只报告，不猜（避免变成两条同 slug）"""
    _card(
        tmp_path / "methodology" / "2026-09-10-x-not-loc.md",
        "type: methodology\ntags: [x]\nupdated: '2026-09-10'\nstatus: active\n"
        "reuse_count: 0\ntitle: x-and-y-not-loc",
    )
    _index(
        tmp_path,
        "## 方法论（methodology/）\n- x-and-y-not-loc    描述甲\n- 2026-09-10-x-not-loc    描述乙\n",
    )
    res = scan(tmp_path)
    assert res["ghost_fixable"] == []
    assert len(res["ghost_manual"]) == 1


def test_prose_bullets_are_not_bare_registrations(tmp_path):
    """使用约定/沉淀通道分区里的散文行不应被当成裸登记行"""
    _index(
        tmp_path,
        "## 使用约定（各平台执行前必读）\n- 确定性：直接读对应目录文件。\n"
        "## 沉淀通道\n- **各平台内容先写入** .sync/drafts/\n",
    )
    assert scan(tmp_path)["bare"] == []


def test_bare_registration_detected_in_card_section(tmp_path):
    _index(tmp_path, "## 经验（experience/）\n- some-card-without-desc\n")
    assert scan(tmp_path)["bare"] == [(2, "some-card-without-desc")]


def test_unregistered_authority_file_detected(tmp_path):
    _card(
        tmp_path / "projects" / "T99-todo.md",
        "type: project\ntags: [x]\nupdated: '2026-09-10'\nstatus: active\nreuse_count: 0",
    )
    _index(tmp_path, "## 项目记忆（projects/）\n- other    描述文本\n")
    assert ("projects", "T99-todo.md") in scan(tmp_path)["unregistered"]
