# @version V1.0 / 2026-09-24 / 双通道融合的「强证据不被淹没」契约
"""融合层回归：向量冠军保底 + 通道权重。

## 背景（2026-09-24，P0-B 真因）

22 条金标准实测暴露：`hypothesis-property-based-testing-blueprint` 在**向量通道是第 1 名**
（相似度 0.6704，领先第 2 名 0.107），却在 RRF 融合结果里**掉出 top-5** ——
因为 RRF 只看位序不看强度，"两通道都上榜"的普通卡各拿两份 rank 分，反超"只有向量命中"的强目标。

两条修法各有契约，本文件分别钉死：
1. `_with_vector_champion`：向量榜首被挤出时必须补进首位（补的是**证据**，不是偏爱）
2. `_rrf_fuse` 的通道权重：向量通道权重 > 词袋（词袋在中文短查询上噪声大）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.frontmatter import Card
from tools.retrieve import (
    _RRF_K,
    _VEC_WEIGHT,
    _WORD_WEIGHT,
    _rrf_fuse,
    _with_vector_champion,
)


def _card(slug: str, ctype: str = "exp") -> Card:
    return Card(type=ctype, path=Path(f"C:/hub/{ctype}/{slug}.md"))


def test_champion_promoted_to_front_when_crowded_out():
    """向量榜首不在融合结果里 ⇒ 补进首位，其余顺延（不丢原结果）。"""
    champ = _card("vector-champion", "blueprint")
    fused = [(_card("a"), 0.03), (_card("b"), 0.029)]
    vec = [(champ, 0.67), (_card("a"), 0.55)]

    out = _with_vector_champion(fused, vec, top_k=3)

    assert [c.path.stem for c, _ in out] == ["vector-champion", "a", "b"]


def test_champion_not_duplicated_when_already_present():
    """榜首已在结果里 ⇒ 次序完全不变（保底不得变成偏爱）。"""
    champ = _card("vector-champion")
    fused = [(_card("a"), 0.03), (champ, 0.02), (_card("b"), 0.01)]

    out = _with_vector_champion(fused, [(champ, 0.67)], top_k=3)

    assert [c.path.stem for c, _ in out] == ["a", "vector-champion", "b"]


def test_champion_noop_when_vector_channel_empty():
    """向量通道没有结果（未建库/后端缺失）⇒ 不得凭空造卡片。"""
    fused = [(_card("a"), 0.03), (_card("b"), 0.02)]
    assert _with_vector_champion(fused, [], top_k=2) == fused


def test_champion_keeps_top_k_size():
    """补首位不得让结果集变大（调用方按 top_k 消费）。"""
    fused = [(_card(f"c{i}"), 0.1 - i * 0.01) for i in range(5)]
    out = _with_vector_champion(fused, [(_card("champ"), 0.9)], top_k=5)
    assert len(out) == 5
    assert out[-1][0].path.stem == "c3"  # 末位被挤出，而不是追加成第 6 条


def test_vector_channel_outweighs_word_channel_on_equal_rank():
    """同为第 1 名时，向量通道的卡必须排在词袋通道之前（权重契约）。"""
    word_only = _card("word-first")
    vec_only = _card("vec-first")

    fused = _rrf_fuse([(word_only, 0.9)], [(vec_only, 0.9)], top_k=2)

    assert fused[0][0].path.stem == "vec-first"


def test_word_channel_still_contributes():
    """词袋通道不得被加权归零：两通道都命中的卡仍应强于只命中一个通道的卡。"""
    both = _card("both")
    vec_only = _card("vec-first")
    word = [(both, 0.9), (_card("w2"), 0.5)]
    vec = [(vec_only, 0.9), (both, 0.8)]

    fused = _rrf_fuse(word, vec, top_k=3)

    assert fused[0][0].path.stem == "both"


def test_rrf_score_matches_declared_weights():
    """排名分公式可复算：score = w_word/(k+rank_word) + w_vec/(k+rank_vec)。"""
    c = _card("both")
    fused = _rrf_fuse([(c, 0.9)], [(c, 0.9)], top_k=1)
    expected = (_WORD_WEIGHT + _VEC_WEIGHT) / (_RRF_K + 1)
    assert fused[0][1] == pytest.approx(expected)
