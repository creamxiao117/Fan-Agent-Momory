# hub-engine/tests/test_task_tier.py
from tools.task_tier import L1_CARDS, classify


def test_default_is_light():
    assert classify("今天天气怎么样") == "light"
    assert classify("") == "light"


def test_code_keywords():
    assert classify("帮我 commit 这个改动并跑 ruff") == "code"
    assert classify("修一下这个 patch 的缩进") == "code"
    assert classify("open a PR for this fix") == "code"


def test_hub_keywords():
    assert classify("把经验 ingest 进中枢 rules") == "hub"
    assert classify("查一下 AgentMemoryHub 的 INDEX") == "hub"


def test_sync_keywords():
    assert classify("sync --push 到四个平台") == "sync"
    assert classify("把指令注入 workbuddy") == "sync"


def test_explicit_beats_keyword():
    # 多关键词冲突时：hub > sync > code > light 的固定优先级
    assert classify("ingest 之后 commit 并 sync --push") == "hub"


def test_l1_covers_all_tiers():
    for t in ("light", "code", "hub", "sync"):
        assert t in L1_CARDS
    assert L1_CARDS["light"] == []  # 仅 L0
    assert any(
        "chinese-text-encoding" in c or "encoding" in c for c in L1_CARDS["code"]
    )
    assert "dual-platform-coherence-discipline" in L1_CARDS["hub"]
    assert "cross-platform-sync-rule" in L1_CARDS["sync"]
