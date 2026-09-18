"""commit 作用域回归测试（§4 工作区守护）。

锁定缺陷：`sync._commit` 原用无条件 `git add -A`，会把操作期间**他人/其它进程**
未提交的改动一并卷进本次 commit。2026-09-19 实证：ingest 提交 f93742e 卷入
nightly.log / retro/log.md / cross-platform-sync-rule.md / candidate-1.md 删除 共 4 项。

覆盖：
1. ingest 提交只含本次产物；预置的「他人现场」（已跟踪改动 + 未跟踪）保持未提交
2. 本次无新变化时不产生提交（不空提交、不误提交他人现场）
3. protect=None 的旧调用仍走 add -A（兼容），并且打印告警——防止上游漏改调用点后静默回退
"""

import subprocess
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
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


def _make_draft(root: Path, platform: str, name: str, body: str) -> Path:
    """写一张最小合法 longterm 草稿（低风险类型，ingest 会直接入权威区）。"""
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(
        "---\n"
        "type: longterm\n"
        "tags:\n  - test\n"
        "updated: 2026-09-19\n"
        "status: candidate\n"
        "reuse_count: 0\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return p


def _setup_foreign_scene(root: Path) -> tuple[Path, Path]:
    """造「他人现场」：一个已跟踪被改动的文件 + 一个未跟踪文件。返回两者路径。"""
    tracked = root / "projects" / "foreign-tracked.md"
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("他人基线内容\n", encoding="utf-8")
    _git(root, "add", "projects/foreign-tracked.md")
    _git(root, "commit", "-m", "他人: 基线")
    tracked.write_text("他人正在改的内容（未提交）\n", encoding="utf-8")  # 变脏

    untracked = root / "projects" / "foreign-untracked.md"
    untracked.write_text("他人未跟踪文件\n", encoding="utf-8")
    return tracked, untracked


def test_ingest_commit_does_not_sweep_foreign_changes(tmp_path: Path):
    """本次提交只含 ingest 产物；他人现场必须原样留在工作区。"""
    root = bootstrap(tmp_path)
    tracked, _untracked = _setup_foreign_scene(root)
    _make_draft(root, "trae", "exp-commit-scope.md", "提交作用域测试内容")

    stat = ingest(root, "trae")
    assert stat["promoted"] == 1

    changed = set(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    assert "longterm/exp-commit-scope.md" in changed, "本次产物必须进提交"
    assert "projects/foreign-tracked.md" not in changed, "他人已跟踪改动被卷入提交"
    assert "projects/foreign-untracked.md" not in changed, "他人未跟踪文件被卷入提交"

    dirty = _git(root, "status", "--porcelain")
    assert "projects/foreign-tracked.md" in dirty, "他人改动应仍保持未提交状态"
    assert tracked.read_text(encoding="utf-8").endswith("（未提交）\n")


def test_commit_noop_when_only_foreign_dirty(tmp_path: Path):
    """只有他人现场脏、本次无产出时：不产生任何提交。"""
    root = bootstrap(tmp_path)
    _setup_foreign_scene(root)
    head_before = _git(root, "rev-parse", "HEAD").strip()

    protect = _snapshot_dirty(root)
    _commit(root, "test: 不应产生提交", protect=protect)

    assert _git(root, "rev-parse", "HEAD").strip() == head_before


def test_snapshot_excludes_input_from_commit(tmp_path: Path):
    """快照作为基线：快照后新增的变化才会被提交。"""
    root = bootstrap(tmp_path)
    _setup_foreign_scene(root)
    protect = _snapshot_dirty(root)

    mine = root / "projects" / "mine.md"
    mine.write_text("本次新产出\n", encoding="utf-8")
    _commit(root, "test: 只提交本次新产出", protect=protect)

    changed = set(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    assert changed == {"projects/mine.md"}, f"提交范围应精确为本次产出，实际 {changed}"


def test_legacy_protect_none_still_adds_all_with_warning(tmp_path: Path, capsys):
    """兼容路径：protect=None 仍走 add -A（旧行为），但必须打印告警。"""
    root = bootstrap(tmp_path)
    _setup_foreign_scene(root)

    mine = root / "projects" / "mine.md"
    mine.write_text("本次新产出\n", encoding="utf-8")
    _commit(root, "test: legacy add -A", protect=None)

    changed = set(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    assert "projects/mine.md" in changed
    assert "projects/foreign-untracked.md" in changed, (
        "legacy 路径应保持旧行为（全部 add）"
    )
    assert "警告" in capsys.readouterr().out


def test_snapshot_parses_chinese_and_rename(tmp_path: Path):
    """快照须能解析中文路径（依赖 core.quotepath=false）与 rename 记录。"""
    root = bootstrap(tmp_path)
    cn = root / "projects" / "中文名文件.md"
    cn.write_text("中文路径内容\n", encoding="utf-8")

    snap = _snapshot_dirty(root)
    assert "projects/中文名文件.md" in snap, f"中文路径未进入快照: {snap}"

    _git(root, "add", "projects/中文名文件.md")
    _git(root, "commit", "-m", "他人: 中文基线")
    _git(root, "mv", "projects/中文名文件.md", "projects/改名后.md")
    assert "projects/改名后.md" in _snapshot_dirty(root)
