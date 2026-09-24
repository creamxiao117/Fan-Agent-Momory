"""确定性通道短路门禁的回归测试（2026-09-24）。

## 背景：生产检索召回曾被这条短路打到 recall@1 = 5%

旧代码 `retrieve_with_meta` 里是：

    hits = deterministic_retrieve(root, query, mode, tags=tags)
    if hits:                                   # ← 只要有命中就短路
        return "deterministic", [(c, None) for c in hits]

而 `deterministic_retrieve` 在 word 模式下按「查询词 ⊂ tag」匹配，**部分词命中也算命中**：

- 查询「写锁 僵尸」→ 某卡 tag 叫 `写锁`（只命中 1/2 词）→ 返回 1 张 → **短路**，
  词袋与向量通道全被跳过（纯 RRF 下目标卡其实稳居第 1 名）
- 查询「embedding model switch drift」→ 英文查询阈值为 2，仅 tag `model-switch`
  命中 2 词 → 返回 `deepseek-peak-offpeak-scheduler` → **短路**

实测（20 条金标准）：生产模式 recall@5 65%→**100%**、recall@1 **5%**→**80%**。

本测试锁死「部分命中不得短路」这一不变式。
"""

from __future__ import annotations

from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.retrieve import _det_is_decisive, retrieve_with_meta


class _Card:
    """最小卡桩：只需 type / tags。"""

    def __init__(self, ctype: str, tags: list[str]) -> None:
        self.type = ctype
        self.tags = tags


def _seed(root: Path) -> None:
    """种两张卡：一张 tag 只部分匹配，一张是真正的目标。

    - `partial.md` 的 tag 恰好是查询的第一个词（旧实现据此短路，抢走正确结果）
    - `target.md` 才真正相关，但在确定性通道里拿不到 tag 命中
    """
    (root / "rules" / "partial.md").write_text(
        "---\ntype: exp\ntags: [写锁]\nupdated: 2026-09-24\nstatus: active\nreuse_count: 0\n---\n"
        "（本卡只声明了 写锁 这一个 tag，与查询只部分重合。）\n",
        encoding="utf-8",
    )
    (root / "rules" / "target.md").write_text(
        "---\ntype: exp\ntags: [zombie, lock]\nupdated: 2026-09-24\nstatus: active\nreuse_count: 0\n---\n"
        "写锁残留会导致僵尸锁：进程崩溃后未释放的锁文件，使后续写入一直失败。\n",
        encoding="utf-8",
    )


# ── 纯函数：判定逻辑 ────────────────────────────────────────────────────────


def test_partial_word_match_is_not_decisive():
    """只命中部分查询词 → 不足以定论（不得短路）。"""
    card = _Card("exp", ["写锁"])
    assert _det_is_decisive("写锁 僵尸", [card]) is False


def test_all_words_matched_is_decisive():
    """全部查询词都命中该卡 tag → 可定论。"""
    card = _Card("exp", ["写锁", "僵尸"])
    assert _det_is_decisive("写锁 僵尸", [card]) is True


def test_exact_tag_is_decisive():
    """整句就是某个 tag → 可定论（保留快路径）。"""
    card = _Card("exp", ["写锁"])
    assert _det_is_decisive("写锁", [card]) is True


def test_type_match_is_decisive():
    """整句命中 type → 可定论。"""
    card = _Card("rule", ["something-else"])
    assert _det_is_decisive("rule", [card]) is True


def test_empty_inputs_are_not_decisive():
    """空查询 / 空结果 → 不定论。"""
    assert _det_is_decisive("", [_Card("rule", ["x"])]) is False
    assert _det_is_decisive("写锁 僵尸", []) is False


# ── 端到端：通道选择 ────────────────────────────────────────────────────────


def test_partial_deterministic_hit_does_not_shortcircuit(tmp_path):
    """核心回归：部分命中的确定结果必须放行给语义通道。

    旧实现下这里会返回 channel == "deterministic" 且内容是 `partial.md`，
    正确卡 `target.md` 永不出现在结果里。
    """
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "写锁 僵尸", top_k=5, mode="word")
    names = [c.path.name for c, _ in scored]
    assert channel == "semantic", f"部分命中不应短路，实际 channel={channel}"
    assert "target.md" in names, f"正确卡未召回：{names}"


def test_exact_tag_still_shortcircuits(tmp_path):
    """反向保护：整句命中 tag 时仍走快路径（不得把短路一律废掉）。"""
    root = bootstrap(tmp_path)
    _seed(root)
    channel, _ = retrieve_with_meta(root, "写锁", top_k=5, mode="word")
    assert channel == "deterministic"
