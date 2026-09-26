# @version V1.1 / 2026-09-25 / 双通道融合的「强证据不被淹没」契约
"""融合层回归：向量冠军保底 + 通道权重。

## 背景（2026-09-24，P0-B 真因）

22 条金标准实测暴露：`hypothesis-property-based-testing-blueprint` 在**向量通道是第 1 名**
（相似度 0.6704，领先第 2 名 0.107），却在 RRF 融合结果里**掉出 top-5** ——
因为 RRF 只看位序不看强度，"两通道都上榜"的普通卡各拿两份 rank 分，反超"只有向量命中"的强目标。

两条修法各有契约，本文件分别钉死：
1. `_with_vector_champion`：向量榜首被挤出时必须补回结果集（补的是**证据**，不是偏爱）
2. `_rrf_fuse` 的通道权重：向量通道权重 > 词袋（词袋在中文短查询上噪声大）

## V1.1（2026-09-25，D2 实测改）：补**末位**而不是首位

58 条金标准上三种排布对比（word/char @5 / @1）：置首 98%/76% · 100%/69%；
**补末位 98%/78% · 100%/69%**；取消保底 98%/78% · 98%/69%（char @5 掉到 98%）。

原因：补首位时冠军带的是假 `score=0.0`（未参与 RRF），却排在真正双通道命中卡之前 ——
分数与位次语义不一致，且实测榜首常是噪声卡（曾把 `auto-promote-empty-today-rule` 推上首位，
把真实目标挤出 top-5）。补末位保留“不丢强证据”的收益，不再抢位。
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


def test_champion_appended_last_when_crowded_out():
    """向量榜首不在融合结果里 ⇒ 补进**末位**（V1.1：不抢真命中卡的位次）。

    D2 实测背景：补首位时冠军带假 score=0.0 却排在双通道真命中卡之前 ⇒
    word @1 76% ；补末位后 @1 78% 而 @5 不变（保留保底收益）。
    """
    champ = _card("vector-champion", "blueprint")
    fused = [(_card("a"), 0.03), (_card("b"), 0.029)]
    vec = [(champ, 0.67), (_card("a"), 0.55)]

    out = _with_vector_champion(fused, vec, top_k=3)

    assert [c.path.stem for c, _ in out] == ["a", "b", "vector-champion"]
    assert out[-1][1] == 0.0  # 位次与分数语义一致：未参与 RRF ⇒ 最低分放最后


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
    """补末位不得让结果集变大（调用方按 top_k 消费）：末位腾位。"""
    fused = [(_card(f"c{i}"), 0.1 - i * 0.01) for i in range(5)]
    out = _with_vector_champion(fused, [(_card("champ"), 0.9)], top_k=5)
    assert len(out) == 5
    assert out[:4] == fused[:4]
    assert out[-1][0].path.stem == "champ"


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
