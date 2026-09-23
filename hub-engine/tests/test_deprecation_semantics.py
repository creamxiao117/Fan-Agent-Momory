# @version V1.0 / 2026-09-23 / pi / 弃用语义测试：status:deprecated 显式表达 + 两引擎一致排除

"""弃用语义（2026-09-23 重构）。

背景：此前"弃用"靠文件第 1 行的 `<!-- DEPRECATED -->` 注释隐式表达——它使 `---`
不在第 0 字节，frontmatter 解析失败，卡被*被动*丢弃。该机制位置敏感：
为给 frontmatter 加 `tier:` 而把注释下移，作废卡就会"复活"进检索库（A5 踩坑）。

重构后：`status: deprecated` + `superseded_by` 显式表达，且：
- 两个引擎（中枢 hub-engine/cards.py、项目 hub-engine/tools/retrieve.py）一致排除
- frontmatter 合法 ⇒ lint 不再报 invalid
- 作废状态可被测试证伪（而非依赖字节偏移的副作用）
"""

from pathlib import Path

from common.frontmatter import try_read_card, validate_card
from scripts.bootstrap_hub import bootstrap
from tools.lint import lint
from tools.retrieve import _index


def _write_card(root: Path, rel: str, status: str) -> Path:
    """在 root/rel 写一张最小合法卡（type 由目录推断）"""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    card_type = "rule" if rel.startswith("rules") else "methodology"
    p.write_text(
        "---\n"
        f"type: {card_type}\n"
        "tags: [probe]\n"
        "updated: 2026-09-23\n"
        f"status: {status}\n"
        "reuse_count: 0\n"
        "---\n"
        f"# {rel} 的卡片正文\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------- 校验层


def test_validate_card_accepts_deprecated_status(tmp_path):
    """deprecated 必须进入合法 status 白名单，否则全新的显式弃用会被判 invalid"""
    root = bootstrap(tmp_path)
    card = try_read_card(_write_card(root, "rules/dep.md", "deprecated"))
    assert card is not None, "deprecated 卡应能被解析"
    assert card.status == "deprecated"
    assert validate_card(card) == [], (
        f"deprecated 不应产生校验错误: {validate_card(card)}"
    )


def test_lint_does_not_flag_deprecated_as_invalid(tmp_path):
    """显式弃用卡 frontmatter 合法 → lint 的 invalid 与 schema_drift 均为空"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/dep.md", "deprecated")
    report = lint(root)
    assert report["invalid"] == 0, f"invalid 应为 0，实际 {report['invalid']}"
    assert report["schema_drift"] == [], (
        f"schema_drift 应为空，实际 {report['schema_drift']}"
    )


# ---------------------------------------------------------------- 检索层（项目引擎）


def test_deprecated_card_excluded_from_retrieval_index(tmp_path):
    """作废卡不得进检索索引（否则会把已并入他卡的旧副本喂给模型）"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/keep.md", "active")
    _write_card(root, "rules/gone.md", "deprecated")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "keep.md" in names, "active 卡应在检索索引中"
    assert "gone.md" not in names, "deprecated 卡不应进检索索引"


def test_archived_card_still_excluded_from_retrieval_index(tmp_path):
    """archived 仍被排除（本次改动不得回归掉既有行为）"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/keep.md", "active")
    _write_card(root, "rules/arch.md", "archived")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "keep.md" in names
    assert "arch.md" not in names


def test_candidate_and_reference_remain_retrievable(tmp_path):
    """candidate / reference 不在排除集合内——不得误伤（它们是合法可检索状态）"""
    root = bootstrap(tmp_path)
    _write_card(root, "methodology/cand.md", "candidate")
    _write_card(root, "methodology/ref.md", "reference")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "cand.md" in names, "candidate 应可检索"
    assert "ref.md" in names, "reference 应可检索"


# ---------------------------------------------------------------- 常量同口径（防两引擎漂移）


def test_project_engine_excluded_statuses_matches_hub_engine():
    """两套引擎的排除集合必须一致——历史上"两套实现各写各的"已多次造成漂移"""
    import importlib.util
    import sys

    from tools import retrieve as proj_retrieve

    hub_cards_py = (
        Path(__file__).resolve().parents[2]
        / "AgentMemoryHub"
        / "hub-engine"
        / "cards.py"
    )
    assert hub_cards_py.exists(), f"未找到中枢 cards.py: {hub_cards_py}"

    spec = importlib.util.spec_from_file_location("_hub_cards_probe", hub_cards_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_hub_cards_probe"] = mod
    spec.loader.exec_module(mod)

    assert set(proj_retrieve.EXCLUDED_STATUSES) == set(mod.EXCLUDED_STATUSES), (
        "项目引擎与中枢引擎的排除状态集合不一致："
        f"{sorted(proj_retrieve.EXCLUDED_STATUSES)} vs {sorted(mod.EXCLUDED_STATUSES)}"
    )
    assert "deprecated" in proj_retrieve.EXCLUDED_STATUSES
    assert "archived" in proj_retrieve.EXCLUDED_STATUSES
