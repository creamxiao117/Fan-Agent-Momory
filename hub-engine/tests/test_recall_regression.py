"""recall_regression 的轻量测试。

只测**纯逻辑**（金标准集完整性 + 排名判定），不测真实检索：
真实检索依赖向量库与 jieba，属"测量"而非"单测"，由 `python -m scripts.recall_regression` 跑。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.recall_regression import (
    GOLD,
    GOLD_MAX_SLUG_WORDS_IN_QUERY,
    GOLD_SLUG_WORD_ALLOWLIST,
    MODES,
    PRODUCTION_MODE,
    _rank_of,
)


class _FakeCard:
    def __init__(self, name: str) -> None:
        self.path = Path(name)


def test_gold_set_size() -> None:
    """金标准集应有 ≥ 20 条（少于 20 则统计意义不足）。

    2026-09-25 D2 扩到 58 条（@1 在 22 条上已饱和）；集合只能变大或持平，
    若需减少应在 commit message 里说明理由。
    """
    assert len(GOLD) >= 40


def test_gold_slugs_unique_and_nonempty() -> None:
    """slug 唯一且非空；query 非空——否则该条测试无意义。"""
    slugs = [c.slug for c in GOLD]
    assert len(slugs) == len(set(slugs)), "存在重复目标卡"
    assert all(c.slug.strip() for c in GOLD)
    assert all(c.query.strip() for c in GOLD)


def test_gold_queries_not_verbatim_summaries() -> None:
    """查询不得是 slug 的字面改写（防"自欺"：抄原文会让检索容易得毫无意义）。

    判据（2026-09-25 D2 细化）：
    1. slug 中的**描述性**词（≥ 5 字符）不得出现在查询里；
    2. 实体/技术名（`GOLD_SLUG_WORD_ALLOWLIST`）不算泄漏 —— 问"Hypertrace 是干什么的"
       是自然提问，不是抄答案；
    3. 但无论是否在白名单，**任何查询都不得命中 ≥ 3 个 slug 词**（那已是整句 slug 改写）。
    """
    for case in GOLD:
        words = [w for w in case.slug.replace("_", "-").split("-") if len(w) >= 5]
        hits = [w for w in words if w in case.query.lower()]
        leaked = [w for w in hits if w not in GOLD_SLUG_WORD_ALLOWLIST]
        assert not leaked, f"「{case.query}」直接抄了 slug 词 {leaked}"
        assert len(hits) <= GOLD_MAX_SLUG_WORDS_IN_QUERY, (
            f"「{case.query}」命中了 {len(hits)} 个 slug 词 {hits}（上限 {GOLD_MAX_SLUG_WORDS_IN_QUERY}），"
            "等于把卡名改写成问句"
        )


def test_production_mode_is_a_real_mode() -> None:
    """生产模式必须是受支持的模式之一（CLI 默认变更时须同步）。"""
    assert PRODUCTION_MODE in MODES


def test_rank_of_finds_and_misses() -> None:
    """位次判定：命中给 1 起序号，未命中给 None。"""
    hits = [_FakeCard("a.md"), _FakeCard("target.md"), _FakeCard("c.md")]
    assert _rank_of(hits, "target") == 2
    assert _rank_of(hits, "absent") is None
    assert _rank_of([], "target") is None
