"""`_norm_card_path` 回归测试：消除向量检索的 CWD 依赖。

## 背景（2026-09-23 记录、2026-09-24 修复）

`vector.db` 的 `path` 列若存**相对路径**（建库时 `--root` 传了相对路径），
旧实现的 `Path(p).resolve()` 会按**进程 CWD** 解析 ⇒ 仅当 CWD 恰好是项目根时才匹配。
实测：cwd=项目根 向量 3/6；cwd=hub-engine 或用户主目录 **0/6 静默退化**。

生产 MCP 以绝对 `--hub-root` 启动、CWD 继承父进程 ⇒ 向量通道可能长期静默失效，
而**没有任何报错**（检索"只"退化到词袋通道）。

本测试直接对纯函数断言，不依赖向量库与 CWD。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.retrieve import _norm_card_path


def test_absolute_path_is_cwd_independent(tmp_path: Path, monkeypatch) -> None:
    """绝对路径：无论 CWD 在哪，结果一致。"""
    root = tmp_path / "AgentMemoryHub"
    card = root / "rules" / "x.md"
    card.parent.mkdir(parents=True)
    card.write_text("# x\n", encoding="utf-8")

    a = _norm_card_path(card, root)
    monkeypatch.chdir(tmp_path)  # 换 CWD
    b = _norm_card_path(card, root)
    assert a == b
    assert Path(a).is_absolute()


def test_relative_path_resolves_against_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    """核心回归：相对路径按 **root** 解析。

    同一相对路径在两个不同 CWD 下必须得到**同一**结果 —— 旧实现会给出两个不同结果
    （按 CWD 解析），这正是 bug 的形态。
    """
    root = tmp_path / "AgentMemoryHub"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "x.md").write_text("# x\n", encoding="utf-8")

    rel = Path("rules") / "x.md"  # 相对 root

    monkeypatch.chdir(tmp_path)
    from_tmp = _norm_card_path(rel, root)

    monkeypatch.chdir(root)  # 旧实现在此会解析成 root/rules/x.md，与上面不同
    from_root = _norm_card_path(rel, root)

    assert from_tmp == from_root, "相对路径解析结果随 CWD 变化 = CWD 依赖未除根"
    assert from_tmp == str((root / "rules" / "x.md").resolve()).lower()


def test_relative_path_with_hub_prefix(tmp_path: Path, monkeypatch) -> None:
    """历史形态：库里存的是「含 AgentMemoryHub 前缀」的相对路径。"""
    proj = tmp_path / "proj"
    root = proj / "AgentMemoryHub"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "x.md").write_text("# x\n", encoding="utf-8")

    # 相对的是 root 的父目录
    rel = Path("AgentMemoryHub") / "rules" / "x.md"

    monkeypatch.chdir(tmp_path)
    got = _norm_card_path(rel, root)
    assert got == str((root / "rules" / "x.md").resolve()).lower()


def test_lowercased_for_windows_case_insensitivity(tmp_path: Path) -> None:
    """统一小写：Windows 大小写不敏感，避免同一路径两种写法匹配不上。"""
    root = tmp_path / "AgentMemoryHub"
    card = root / "Rules" / "X.md"
    card.parent.mkdir(parents=True)
    card.write_text("# x\n", encoding="utf-8")
    assert _norm_card_path(card, root) == _norm_card_path(card, root).lower()
