"""post_ingest_hook._commit_indices 的提交面回归测试（2026-11-13 治本）。

锁定缺陷：旧实现是「`git add <INDEX>` + `git commit`」⇒ 提交的是**整个索引** ⇒
  ① 卷走他人已 `git add` 但未提交的改动；
  ② 提交里可能带**陈旧 INDEX**（缺本轮新卡）⇒ l0 门禁（判据 = 暂存态）判不一致
     ⇒ 阻断 ⇒ 该批产物永久滞留暂存区 ⇒ 之后每次提交都被同一个 l0 挡下（流水线卡死）。

覆盖：
  1. 提交里的 INDEX 与**该提交里的**卡集合一致（无幽灵登记）；
  2. 他人**已暂存**的改动不被本次提交带走、也不被幽灵登记；
  3. 幂等重跑不产生新提交（返回 True）；
  4. 提交树上的卡不合法 ⇒ fail-closed（返回 False ⇒ 调用方退出码 3）。
"""

import subprocess
from pathlib import Path

from common.authority import CARD_DIRS
from scripts.bootstrap_hub import bootstrap
from scripts.post_ingest_hook import _commit_indices
from scripts.render_index import parse_entries
from scripts.render_index import write as render_write

RENDERED = ("INDEX.md", "INDEX-full.md", "INDEX-experience.md")


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return r.stdout or ""


def _card_text(body: str) -> str:
    """一张**合法**卡的文本（权威区里的 .md 就是卡 ⇒ 裸文本 .md 是非法卡）。"""
    return (
        "---\ntype: project\ntags:\n  - test\nupdated: 2026-11-13\n"
        "status: active\nreuse_count: 0\n---\n\n# 测试卡\n\n" + body.rstrip("\n") + "\n"
    )


def _write_card(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_card_text(body), encoding="utf-8")
    return p


def _render(root: Path) -> None:
    assert render_write(root, lock=False) == []


def _make_hub(tmp_path: Path) -> Path:
    """可提交的中枢：bootstrap + 一张基线卡 + 已渲染的 INDEX（全部已提交）。"""
    root = bootstrap(tmp_path)
    _write_card(root, "longterm/base-card.md", "基线卡：hook 提交面测试的起点。")
    _render(root)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local", "commit", "-m", "基线")
    return root


def _commit_card_slugs(root: Path, ref: str = "HEAD") -> set[str]:
    out = _git(root, "ls-tree", "-r", "--name-only", ref)
    slugs: set[str] = set()
    for line in out.splitlines():
        p = line.strip()
        if not p.endswith(".md"):
            continue
        parts = p.split("/")
        if len(parts) == 2 and parts[0] in CARD_DIRS:
            slugs.add(parts[1][:-3])
    return slugs


def _commit_index_slugs(root: Path, ref: str = "HEAD") -> set[str]:
    slugs: set[str] = set()
    for name in ("INDEX-full.md", "INDEX-experience.md"):
        try:
            text = _git(root, "show", f"{ref}:{name}")
        except subprocess.CalledProcessError:
            continue
        slugs |= set(parse_entries(text))
    return slugs


def _stale_index_scene(root: Path) -> None:
    """制造「卡已提交、INDEX 陈旧」的历史现场（旧的 l0 死锁的触发态）。"""
    _write_card(root, "longterm/card-b.md", "已提交但索引陈旧的卡。")
    _render(root)
    _git(root, "add", "longterm/card-b.md")
    _git(root, "-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local", "commit", "-m", "只提交卡")


def test_hook_commit_index_matches_commit_cards(tmp_path: Path):
    """判据①：提交里的 INDEX 与该提交里的卡集合一致（无幽灵登记）。"""
    root = _make_hub(tmp_path)
    _stale_index_scene(root)

    assert _commit_indices(root, set(RENDERED), []) is True

    cards = _commit_card_slugs(root)
    index = _commit_index_slugs(root)
    assert cards == {"base-card", "card-b"}
    assert index == cards, f"提交里的 INDEX 与卡集合不一致：多 {index - cards} / 少 {cards - index}"


def test_hook_commit_does_not_sweep_foreign_staged_card(tmp_path: Path):
    """判据②：他人**已暂存**的卡不被本次提交带走，也不被幽灵登记进 INDEX。"""
    root = _make_hub(tmp_path)
    _stale_index_scene(root)
    foreign = "longterm/foreign-staged.md"
    _write_card(root, foreign, "他人已暂存但未提交的卡。")
    _git(root, "add", foreign)
    _render(root)

    assert _commit_indices(root, set(RENDERED), []) is True

    changed = set(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    assert foreign not in changed, "他人已暂存的改动被本次提交带走"
    staged = _git(root, "diff", "--cached", "--name-only")
    assert foreign in staged, "他人已暂存的改动必须仍在暂存区"
    cards = _commit_card_slugs(root)
    index = _commit_index_slugs(root)
    assert foreign not in cards
    assert foreign not in index, "幽灵登记：INDEX 列了本次提交里不存在的卡"
    assert index == cards


def test_hook_commit_is_idempotent(tmp_path: Path):
    """判据③：幂等重跑不产生新提交（返回 True，HEAD 不变）。"""
    root = _make_hub(tmp_path)
    _stale_index_scene(root)

    assert _commit_indices(root, set(RENDERED), []) is True
    head_after_first = _git(root, "rev-parse", "HEAD").strip()

    assert _commit_indices(root, set(RENDERED), []) is True
    assert _git(root, "rev-parse", "HEAD").strip() == head_after_first, "幂等重跑产生了多余提交"


def test_hook_commit_returns_false_when_render_fails(tmp_path: Path):
    """判据④：提交树上的卡不合法 ⇒ fail-closed（返回 False ⇒ 退出码 3）。"""
    root = _make_hub(tmp_path)
    bad = root / "longterm" / "bad-card.md"
    bad.write_text(
        "---\ntype: 不存在的类型\nstatus: active\nupdated: 2026-11-13\n---\n\n坏卡\n",
        encoding="utf-8",
    )
    _git(root, "add", "longterm/bad-card.md")
    _git(root, "-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local", "commit", "-m", "塞进一张坏卡")
    head_before = _git(root, "rev-parse", "HEAD").strip()
    # 制造「INDEX 与 HEAD 不同」⇒ 走到提交这一步（而不是被幂等预检短路）
    (root / "INDEX.md").write_text(
        (root / "INDEX.md").read_text(encoding="utf-8") + "\n手工追加一行\n", encoding="utf-8"
    )

    assert _commit_indices(root, {"INDEX.md"}, []) is False
    assert _git(root, "rev-parse", "HEAD").strip() == head_before, "fail-closed ⇒ 不得产生提交"
