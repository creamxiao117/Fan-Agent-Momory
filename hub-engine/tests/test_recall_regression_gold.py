"""金标准集（recall_regression.GOLD）的夹具体检 —— 防「目标卡漂移导致度量失效」。

2026-09-25 D2 实测背景：扩写金标准时初稿里 2 条目标卡已是 `deprecated`（内容并入别卡），
检索按设计排除废弃卡 ⇒ “未命中”其实是夹具造错；同时发现原 22 条里有 3 条目标卡是
`candidate`（临时态）。本测试把这两类错法钉死。
"""

from pathlib import Path

import pytest

from scripts.recall_regression import GOLD, GOLD_VALID_STATUS, validate_gold

_HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"


def _card(tmp: Path, rel: str, status: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntype: exp\ntags: [x]\nupdated: '2026-09-25'\nstatus: {status}\n---\n\n正文\n",
        encoding="utf-8",
    )


def test_validator_flags_missing_target(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.recall_regression.GOLD",
        (type(GOLD[0])("提问", "不存在的卡"),),
    )
    problems = validate_gold(tmp_path)
    assert len(problems) == 1
    assert "目标卡不存在" in problems[0]


@pytest.mark.parametrize("status", ["deprecated", "archived", "candidate"])
def test_validator_rejects_non_authoritative_target(tmp_path, monkeypatch, status):
    """废弃/归档/临时卡都不能当金标准目标（检索排除前者；后者随时可能被并入）"""
    _card(tmp_path, "experience/t.md", status)
    monkeypatch.setattr("scripts.recall_regression.GOLD", (type(GOLD[0])("提问", "t"),))
    problems = validate_gold(tmp_path)
    assert len(problems) == 1
    assert f"status={status}" in problems[0]


@pytest.mark.parametrize("status", GOLD_VALID_STATUS)
def test_validator_accepts_authoritative_target(tmp_path, monkeypatch, status):
    _card(tmp_path, "experience/t.md", status)
    monkeypatch.setattr("scripts.recall_regression.GOLD", (type(GOLD[0])("提问", "t"),))
    assert validate_gold(tmp_path) == []


def test_validator_flags_duplicate_query(tmp_path, monkeypatch):
    _card(tmp_path, "experience/t.md", "active")
    case = type(GOLD[0])
    monkeypatch.setattr(
        "scripts.recall_regression.GOLD",
        (case("同一个提问", "t"), case("同一个提问", "t")),
    )
    problems = validate_gold(tmp_path)
    assert any("重复查询" in p for p in problems)


def test_gold_size_meets_d2_target():
    """D2 目标 ≥ 40 条（扩前 22 条 @1 已饱和）；缩小集合需要显式改这条测试并说明理由"""
    assert len(GOLD) >= 40
    assert len({c.query for c in GOLD}) == len(GOLD), "查询不得重复"


@pytest.mark.skipif(not _HUB.is_dir(), reason="需要真实中枢仓（CI 无此仓时跳过）")
def test_real_gold_is_healthy():
    """真实金标准集必须通过体检 —— 卡被改名/归档后这条会先红"""
    assert validate_gold(_HUB) == []
