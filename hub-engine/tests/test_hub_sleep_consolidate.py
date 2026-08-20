"""中枢夜间离线自进化候选（SkillOpt-Sleep 纪律落地）单测。

覆盖：收割+挖掘（P0 优先、ok 剔除）、有界候选截断、当前命中标注、
暂存产物（md+json 落盘、不写权威区）、Markdown 渲染含草稿与采纳提示。
"""

import json

from scripts.hub_sleep_consolidate import (
    _render_markdown,
    enrich_current_hits,
    harvest_candidates,
    stage_proposal,
)
from scripts.missing_query import LOG


def _write_log(root, records):
    p = root / LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8"
    )


def _search(query, hit_count, channel="semantic"):
    return {
        "ts": "2026-08-20T00:00:00Z",
        "action": "search",
        "platform": "test",
        "ok": True,
        "query": query,
        "channel": channel,
        "hit_count": hit_count,
    }


def test_harvest_bounded_prefers_p0(tmp_path):
    """P0 全未命中应排最前，且受 max_candidates 有界截断；稳定命中剔除。"""
    recs = [_search("DLL 并发锁", 0) for _ in range(3)]
    recs += [_search("某低命中词", 1) for _ in range(2)]
    recs += [_search("稳定命中词", 5) for _ in range(1)]
    _write_log(tmp_path, recs)

    cands = harvest_candidates(tmp_path, since=None, max_candidates=2)
    assert len(cands) == 2
    assert cands[0]["stage"].startswith("P0")
    assert cands[0]["query"] == "DLL 并发锁"
    assert all(c["stage"] != "ok-无需处理" for c in cands)


def test_harvest_uses_since_window(tmp_path):
    """全局无过滤时，P0 候选可被收割。"""
    _write_log(tmp_path, [_search("窗口内缺口", 0) for _ in range(2)])
    cands = harvest_candidates(tmp_path, since=None, max_candidates=5)
    assert any(c["query"] == "窗口内缺口" for c in cands)


def test_harvest_empty_no_candidates(tmp_path):
    """无 search 记录 → 空候选。"""
    _write_log(tmp_path, [])
    assert harvest_candidates(tmp_path, since=None, max_candidates=5) == []


def test_enrich_current_hits(tmp_path, monkeypatch):
    """当前命中标注：复用 retrieve_with_meta 只读标注 channel/hits，不改候选结构。"""
    _write_log(tmp_path, [_search("缺口 A", 0) for _ in range(3)])
    cands = harvest_candidates(tmp_path, since=None, max_candidates=1)

    def fake_retrieve(root, query, top_k=None):
        return "semantic", [("card1", 0.9)]

    monkeypatch.setattr(
        "scripts.hub_sleep_consolidate.retrieve_with_meta", fake_retrieve
    )
    enriched = enrich_current_hits(cands, tmp_path, top_k=5)
    assert enriched[0]["current_channel"] == "semantic"
    assert enriched[0]["current_hits"] == 1


def test_stage_writes_under_sleep_only(tmp_path):
    """暂存只写 .sync/state/sleep/<ts>/，不触碰权威区，且含该候选。"""
    _write_log(tmp_path, [_search("缺口 B", 0) for _ in range(3)])
    cands = harvest_candidates(tmp_path, since=None, max_candidates=3)
    stage_proposal(tmp_path, cands)

    md = tmp_path.joinpath(".sync/state/sleep")
    assert md.is_dir()
    proposal_json = next(md.glob("*/proposal.json"))
    payload = json.loads(proposal_json.read_text(encoding="utf-8"))
    assert any(c["query"] == "缺口 B" for c in payload["candidates"])
    # 权威区未被写入
    assert not (tmp_path / "experience").exists()
    assert not (tmp_path / "rules").exists()


def test_render_markdown_contains_draft_and_adopt_hint():
    cands = [
        {
            "query": "护 DLL 版本",
            "count": 4,
            "zero_ratio": 1.0,
            "avg_hit": 0.0,
            "channels": ["semantic"],
            "stage": "P0-新增卡片",
            "current_channel": "semantic",
            "current_hits": 0,
        }
    ]
    md = _render_markdown(cands, {"date": "2026-08-20"})
    assert "P0" in md
    assert "ingest" in md
    assert "护 DLL 版本" in md
