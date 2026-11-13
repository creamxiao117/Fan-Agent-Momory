"""提交自洽回归测试（2026-11-13 修 l0 门禁死锁）。

锁定缺陷（2026-11-13 实测）：`sync._commit` 原先是「`git add -- <mine>` + `git commit`」，
带来两个后果：

  ① `git commit` 提交的是**整个索引** ⇒ 别人已 `git add` 但未提交的改动被一并带走；
  ② INDEX 的渲染发生在 `_snapshot_dirty` **之后** ⇒ INDEX.md 早已 dirty ⇒ 被 protect
     排除 ⇒ 不进 mine ⇒ 提交里带的是**陈旧 INDEX**（缺本轮新卡）
     ⇒ pre-commit 的 l0 门禁拿**暂存态**重渲染后比对 ⇒ 不一致 ⇒ 阻断提交
     ⇒ 该批产物永久滞留暂存区 ⇒ 之后每次提交都被同一个 l0 挡下（流水线整体卡死）。

覆盖：
  1. 不变式①：提交里的 INDEX 与**该提交里的卡集合**一致（不得有幽灵登记）
  2. 缺陷复现：「INDEX 先渲染、快照后取」（陈旧 staged INDEX）⇒ 提交**成功**且自洽
  3. 别人**已暂存**的改动不被本次提交带走（且暂存区整体仍自洽 ⇒ 下一个提交能过 l0）
  4. 提交完成后工作树 `render_index --check` 仍 PASS
  5. 提交树上的卡不合法 ⇒ fail-closed（不提交）+ 明确可执行的报错
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from common.authority import CARD_DIRS
from scripts.bootstrap_hub import bootstrap
from scripts.render_index import check as render_check
from scripts.render_index import parse_entries
from scripts.render_index import write as render_write
from sync import _commit, _snapshot_dirty, ingest


def _git(root: Path, *args: str) -> str:
    """在测试仓库里跑 git，返回 stdout（固定 UTF-8 解码，避免中文路径乱码）。"""
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return r.stdout or ""


def _card_text(body: str) -> str:
    """一张**合法**卡的文本。

    ⚠️ 权威区里的 .md **就是卡**（hub_registry 的扫描口径）⇒ 裸文本 .md 是**非法卡**
    ⇒ INDEX 渲染 fail-closed（与 l0 门禁同口径）⇒ 夹具必须写成合法卡。
    """
    return (
        "---\ntype: project\ntags:\n  - test\nupdated: 2026-11-13\n"
        "status: active\nreuse_count: 0\n---\n\n# 测试卡\n\n" + body.rstrip("\n") + "\n"
    )


def _write_card(root: Path, rel: str, body: str) -> Path:
    """写一张合法卡（相对中枢根）。"""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_card_text(body), encoding="utf-8")
    return p


def _make_draft(root: Path, platform: str, name: str, body: str) -> Path:
    """写一张最小合法 longterm 草稿（低风险类型，ingest 会直接入权威区）。"""
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(
        f"---\ntype: longterm\ntags:\n  - test\nupdated: 2026-11-13\nstatus: candidate\nreuse_count: 0\n---\n{body}\n",
        encoding="utf-8",
    )
    return p


def _render(root: Path) -> None:
    """渲染工作树的 INDEX 三件套（渲染器是 INDEX 的唯一写入口）。"""
    assert render_write(root, lock=False) == []


def _make_hub(tmp_path: Path) -> Path:
    """一个可提交的中枢：bootstrap + 一张合法基线卡 + 已渲染的 INDEX（全部已提交）。"""
    root = bootstrap(tmp_path)
    _write_card(root, "longterm/base-card.md", "基线卡：提交自洽测试的起点。")
    _render(root)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local", "commit", "-m", "基线")
    return root


def _commit_card_slugs(root: Path, ref: str = "HEAD") -> set[str]:
    """该提交里的卡 slug 集合（权威区 .md 的 stem）。"""
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
    """该提交里的 INDEX 登记 slug 集合（INDEX-full + INDEX-experience 两个分册）。"""
    slugs: set[str] = set()
    for name in ("INDEX-full.md", "INDEX-experience.md"):
        try:
            text = _git(root, "show", f"{ref}:{name}")
        except subprocess.CalledProcessError:  # 该分册不存在（尚未渲染过）
            continue
        slugs |= set(parse_entries(text))
    return slugs


def _staged_render_errors(root: Path) -> list[str]:
    """**l0 门禁口径**：物化 index → 在其上跑 render_index --check（空 = 一致）。"""
    with tempfile.TemporaryDirectory(prefix="test-index-") as td:
        tree = Path(td) / "tree"
        tree.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-C", str(root), "checkout-index", "-a", f"--prefix={tree}{os.sep}"],
            check=True,
            capture_output=True,
        )
        return render_check(tree)


def _worktree_render_errors(root: Path) -> list[str]:
    """工作树态的 render_index --check（空 = 一致）。"""
    return render_check(root)


def test_commit_index_matches_commit_cards(tmp_path: Path):
    """不变式①：提交里的 INDEX 与该提交里的卡集合一致（无幽灵登记）。"""
    root = _make_hub(tmp_path)
    _make_draft(root, "trae", "exp-invariant.md", "提交自洽不变式测试内容")

    stat = ingest(root, "trae")
    assert stat["promoted"] == 1

    cards = _commit_card_slugs(root)
    index = _commit_index_slugs(root)
    assert index == cards, f"提交里的 INDEX 与卡集合不一致：多 {index - cards} / 少 {cards - index}"


def test_stale_dirty_index_does_not_block_commit(tmp_path: Path):
    """缺陷复现：「INDEX 先渲染、快照后取」⇒ 陈旧 INDEX 曾进提交 ⇒ l0 门禁阻断。

    复现手法：先让工作树的 INDEX 变脏（= 取快照时它已在 protect 里），再跑一轮入库。
    修复后：提交**成功**，且提交里的 INDEX 与该提交里的卡严格一致。
    """
    root = _make_hub(tmp_path)
    # ① 快照前的「他人现场」：一张未提交的卡 + 已渲染但未提交的 INDEX
    _write_card(root, "longterm/foreign-uncommitted.md", "他人未提交的卡（不该进本次提交）。")
    _render(root)
    assert "INDEX.md" in _git(root, "status", "--porcelain"), "前提：INDEX 必须已是 dirty"
    # ② 本轮入库
    _make_draft(root, "trae", "exp-self-consistent.md", "提交自洽回归测试内容")

    stat = ingest(root, "trae")
    assert stat["promoted"] == 1
    # ③ 提交成功且自洽
    cards = _commit_card_slugs(root)
    index = _commit_index_slugs(root)
    assert "exp-self-consistent" in cards, "本次产物必须进提交"
    assert "foreign-uncommitted" not in cards, "他人未提交的卡被卷进本次提交"
    assert index == cards, f"提交里的 INDEX 与卡集合不一致：多 {index - cards} / 少 {cards - index}"
    assert "foreign-uncommitted" not in index, "幽灵登记：INDEX 列了本次提交里不存在的卡"
    # ④ l0 门禁口径（暂存态）也一致 ⇒ 下一个提交能过
    assert _staged_render_errors(root) == []


def test_foreign_staged_change_not_swept_into_commit(tmp_path: Path):
    """别人**已暂存**的改动不被本次提交带走；且暂存区整体仍自洽（下一个提交能过 l0）。"""
    root = _make_hub(tmp_path)
    foreign = "longterm/foreign-staged.md"
    _write_card(root, foreign, "他人已暂存但未提交的卡。")
    _git(root, "add", foreign)
    _make_draft(root, "trae", "exp-scope.md", "提交作用域回归测试内容")

    stat = ingest(root, "trae")
    assert stat["promoted"] == 1

    changed = set(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    assert "longterm/exp-scope.md" in changed, "本次产物必须进提交"
    assert foreign not in changed, "他人已暂存的改动被本次提交带走"
    staged = _git(root, "diff", "--cached", "--name-only")
    assert foreign in staged, "他人已暂存的改动必须仍在暂存区（未被提交、未被撤销）"
    # 本次提交仍自洽（INDEX 不含他人的卡 ⇒ 无幽灵登记）
    cards = _commit_card_slugs(root)
    index = _commit_index_slugs(root)
    assert index == cards, f"提交里的 INDEX 与卡集合不一致：多 {index - cards} / 少 {cards - index}"
    assert "foreign-staged" not in index
    # 暂存区整体自洽 ⇒ 下一个提交能过 l0 门禁（引擎自动重渲染了暂存区的 INDEX）
    assert _staged_render_errors(root) == []


def test_worktree_index_stays_consistent_after_commit(tmp_path: Path):
    """提交完成后工作树态 render_index --check 仍 PASS（不为提交把工作树弄陈旧）。"""
    root = _make_hub(tmp_path)
    _make_draft(root, "trae", "exp-worktree.md", "工作树自洽回归测试内容")

    stat = ingest(root, "trae")
    assert stat["promoted"] == 1

    assert _worktree_render_errors(root) == [], "工作树的 INDEX 与工作树的卡不一致"


def test_invalid_card_in_commit_fails_closed(tmp_path: Path):
    """提交树上的卡不合法 ⇒ fail-closed（不提交）+ 明确可执行的报错。"""
    root = _make_hub(tmp_path)
    head_before = _git(root, "rev-parse", "HEAD").strip()
    protect = _snapshot_dirty(root)  # 快照在前 ⇒ 坏卡算「本轮产物」（否则会被 protect 排除）
    bad = root / "longterm" / "bad-card.md"
    bad.write_text(
        "---\ntype: 不存在的类型\nstatus: active\nupdated: 2026-11-13\n---\n\n坏卡\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as ei:
        _commit(root, "test: 非法卡必须 fail-closed", protect=protect)

    msg = str(ei.value)
    assert "无法自洽" in msg, "报错必须说明现象"
    assert "longterm/bad-card.md" in msg, "报错必须点名非法卡（可执行）"
    assert _git(root, "rev-parse", "HEAD").strip() == head_before, "fail-closed ⇒ 不得产生提交"
