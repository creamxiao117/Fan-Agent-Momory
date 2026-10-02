# @version V1.0 / 2026-10-02 / pi / 能力路由单测（M3/Task 20）
"""`capability_router` 单测：建议必须**可复核**、**负路由优先**、**只建议不安装**。

回归背景：`hub_bootstrap` 原本只返回记忆命中，"该用什么能力"全靠模型临场想。
而能力的触发词与禁用边界早就写在 SkillHub `router.yaml` 里（`trigger`/`forgot`）——
本模块只是把那份既有数据接到任务开头。
"""

from pathlib import Path

import yaml

from tools.capability_router import FORGOT_PENALTY, score_skill, skillhub_router, suggest


def _hub(tmp_path: Path, *, skills: list[dict] | None, router: bool = True) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    skillhub = tmp_path / "SkillHub"
    if router:
        (skillhub / "router").mkdir(parents=True, exist_ok=True)
        (skillhub / "router" / "router.yaml").write_text(
            yaml.safe_dump({"skills": skills or []}, allow_unicode=True), encoding="utf-8"
        )
    (hub / "hub.config.yaml").write_text(
        yaml.safe_dump({"external_paths": {"skillhub": str(skillhub)}}, allow_unicode=True), encoding="utf-8"
    )
    return hub


def _write_capabilities(hub: Path, platform: str, skills: list[str]) -> None:
    import json

    (hub / "system" / "capabilities.json").write_text(
        json.dumps({"skills": {platform: {"count": len(skills), "skills": skills}}}), encoding="utf-8"
    )


def test_score_counts_trigger_and_penalizes_forgot():
    """负路由必须**比命中更重**（"误命中比没有更糟"是 router.yaml 自己写的口径）。"""
    s = {"trigger": ["重构", "测试"], "forgot": ["rule 类型"]}
    sc, hit, bad = score_skill(s, "帮我重构并跑测试")
    assert sc == 2 and hit == ["重构", "测试"] and bad == []
    sc2, _h, bad2 = score_skill(s, "重构 rule 类型 测试")
    assert sc2 == 2 - FORGOT_PENALTY and bad2 == ["rule 类型"]


def test_suggest_returns_why_for_every_item(tmp_path):
    """每条建议必须带 `why`（命中了哪些词），否则用户无从复核——这是硬要求。"""
    hub = _hub(
        tmp_path,
        skills=[
            {"name": "superpowers", "slot": "shared", "invoke": "model", "trigger": ["重构"], "forgot": []},
            {"name": "unrelated", "slot": "shared", "invoke": "model", "trigger": ["区块链"], "forgot": []},
        ],
    )
    r = suggest(hub, "重构检索层", platform="pi")
    names = [s["name"] for s in r["suggested"]]
    assert names == ["superpowers"], names
    assert r["suggested"][0]["why"] and "重构" in r["suggested"][0]["why"]
    assert r["suggested"][0]["invoke"] == "model"


def test_suggest_marks_missing_against_actual_state(tmp_path):
    """账本建议的、磁盘上没有的 → `missing`（这是"任务级临时安装"的输入）。"""
    hub = _hub(
        tmp_path,
        skills=[{"name": "superpowers", "invoke": "model", "trigger": ["重构"], "forgot": []}],
    )
    _write_capabilities(hub, "pi", [])  # 实测态：pi 没装任何技能
    r = suggest(hub, "重构检索层", platform="pi")
    assert [m["name"] for m in r["missing"]] == ["superpowers"]

    _write_capabilities(hub, "pi", ["superpowers"])  # 已装
    r2 = suggest(hub, "重构检索层", platform="pi")
    assert r2["missing"] == []


def test_no_router_returns_empty_not_guessed(tmp_path):
    """SkillHub 不可达 → 返回空（**不猜、不硬编码技能清单**）。"""
    hub = _hub(tmp_path, skills=None, router=False)
    r = suggest(hub, "重构", platform="pi")
    assert r["suggested"] == [] and r["missing"] == []


def test_skillhub_router_reads_single_source(tmp_path):
    hub = _hub(
        tmp_path,
        skills=[{"name": "x", "trigger": ["a"], "forgot": []}],
    )
    data = skillhub_router(hub)
    assert [s["name"] for s in data["skills"]] == ["x"]


def test_note_states_no_auto_install(tmp_path):
    """建议里必须写明"不自动安装"（改客户端配置前需用户批准）。"""
    hub = _hub(tmp_path, skills=[{"name": "x", "trigger": ["重构"], "forgot": []}])
    r = suggest(hub, "重构", platform="pi")
    assert "不自动安装" in r["note"]
