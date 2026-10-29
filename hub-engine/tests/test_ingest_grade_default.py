"""P0-2 回归测试：ingest 落权威区时按目标目录补 grade 默认值。

对应缺陷：飞轮 ingest 的草稿（MCP 建草稿只写 source）落进权威区后缺 grade，
导致巡检 audit 步每天 P0 判红（2026-10-23 起连续 6 天 exit 1）。

跑法（hub-engine 根目录）：
    python -m pytest tests/test_ingest_grade_default.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from common.frontmatter import (  # noqa: E402
    DEFAULT_GRADE_BY_DIR,
    GRADES_BY_DIR,
    parse_card,
)
from sync import _move_non_authority_draft, _promote_or_conflict_draft  # noqa: E402


def _card(type_="exp", body="正文内容", extra=None):
    """构造一张最小草稿卡（frontmatter 里没有 grade）。"""
    fm = ["---", f"type: {type_}", "tags: [pi]", "updated: '2026-10-29'", "status: candidate"]
    if extra:
        fm.append(f"source: {extra}")
    return parse_card("\n".join(fm) + "\n---\n\n" + body + "\n")


def _draft(root: Path, name: str, card) -> Path:
    d = root / ".sync" / "drafts" / "pi_draft"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    from common.frontmatter import write_card

    p.write_text(write_card(card), encoding="utf-8")
    return p


# ── 1) 默认值表自身必须自洽 ──────────────────────────────────────────────
def test_default_grade_by_dir_is_valid_for_each_dir():
    """每个目录的默认 grade 必须落在该目录的合法集内（否则补了也判红）。"""
    for d, g in DEFAULT_GRADE_BY_DIR.items():
        assert g in GRADES_BY_DIR[d], f"{d} 的默认 grade={g} 不在合法集 {sorted(GRADES_BY_DIR[d])}"


def test_default_grade_covers_all_authority_dirs():
    """6 个权威区都要有默认值，否则新卡仍会缺 grade。"""
    assert set(DEFAULT_GRADE_BY_DIR) == set(GRADES_BY_DIR)


# ── 2) promotion 路径：落库时补 grade ──────────────────────────────────
# promotion 路径只处理 TYPE_DIR 里的类型（rule/blueprint/methodology/longterm/project）；
# `exp` 不在其中，走 _move_non_authority_draft → experience/（见下方独立测试）。
@pytest.mark.parametrize(
    ("type_", "expect_dir"),
    [
        ("blueprint", "blueprints"),
        ("project", "projects"),
        ("longterm", "longterm"),
    ],
)
def test_promote_adds_grade_for_each_type(tmp_path: Path, type_: str, expect_dir: str):
    """低风险草稿自动入区后，卡必须带合法 grade。"""
    root = tmp_path / "hub"
    (root / expect_dir).mkdir(parents=True)
    card = _card(type_=type_)
    p = _draft(root, "c1.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _promote_or_conflict_draft(root, "pi", p, card, stat)

    dst = root / expect_dir / "c1.md"
    assert dst.is_file(), "卡应已落盘"
    got = parse_card(dst.read_text(encoding="utf-8"))
    grade = str(got.extra.get("grade") or "")
    assert grade, "落盘卡必须有 grade（否则 audit P0 判红）"
    assert grade in GRADES_BY_DIR[expect_dir], f"grade={grade} 不适用于 {expect_dir}/"


def test_promote_does_not_override_existing_grade(tmp_path: Path):
    """草稿已声明 grade 时不得被默认值覆盖（尊重作者显式取值）。"""
    root = tmp_path / "hub"
    (root / "blueprints").mkdir(parents=True)
    card = _card(type_="blueprint")
    card.extra["grade"] = "proven"
    p = _draft(root, "c2.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _promote_or_conflict_draft(root, "pi", p, card, stat)

    got = parse_card((root / "blueprints" / "c2.md").read_text(encoding="utf-8"))
    assert got.extra.get("grade") == "proven", "显式声明的 grade 必须保留（不得被默认值覆盖）"


# ── 3) 改挪路径：exp 草稿挪进 experience/ 也要补 grade ─────────────────
def test_move_non_authority_adds_grade_for_exp(tmp_path: Path):
    """exp 草稿被挪进 experience/（权威区）时同样要补 grade。"""
    root = tmp_path / "hub"
    (root / "experience").mkdir(parents=True)
    card = _card(type_="exp")
    p = _draft(root, "c3.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _move_non_authority_draft(root, p, card, stat)

    dst = root / "experience" / "c3.md"
    assert dst.is_file()
    got = parse_card(dst.read_text(encoding="utf-8"))
    grade = str(got.extra.get("grade") or "")
    assert grade, "挪进权威区的卡必须有 grade"
    assert grade in GRADES_BY_DIR["experience"]
    assert not p.exists(), "原草稿应已被挪走（不重复留存）"


def test_move_non_authority_leaves_note_untouched(tmp_path: Path):
    """note 草稿挪进 notes/（非权威区）不应被塞 grade。"""
    root = tmp_path / "hub"
    (root / "notes").mkdir(parents=True)
    card = _card(type_="note")
    p = _draft(root, "c4.md", card)
    stat = {"promoted": 0, "promoted_names": [], "duplicate": 0, "moved": 0, "moved_names": []}

    _move_non_authority_draft(root, p, card, stat)

    dst = root / "notes" / "c4.md"
    assert dst.is_file()
    got = parse_card(dst.read_text(encoding="utf-8"))
    assert not str(got.extra.get("grade") or ""), "非权威区不应强行加 grade"
