# @version V1.0 / 2026-09-25 / P1-c 硬编码个人路径护栏
r"""护栏：被跟踪的 Python 代码里不得再出现「个人/本机绝对路径」。

## 为什么需要（审计 2026-09-25 · I-2）

实测 22 个 `.py` 共 47 处写死 `C:/Users/<用户名>/...` 或 `D:/AIwork/...`（含
`bootstrap_hub.py` / `hub_mcp_launcher.py` / `mcp_healthcheck.py` 这类**启动链**文件）。
后果不是"不好看"，而是**换机/换 worktree 后静默失效**：
脚本照跑，只是指向一个不存在的目录 —— 与 2026-09-24 修掉的 `nightly_consolidate.cmd`
硬编码路径属同一缺陷类。

## 判据

- **禁止**：`<盘符>:\Users\<任意用户>\`、`D:/AIwork`（他机盘符）、`20260817-Fan-Agent-Momory`
  （把路径钉死到某个 worktree 名）
- **正确写法**：本仓路径用 `Path(__file__).resolve().parents[n]`；家目录用 `Path.home()`；
  仓外项目用 `common.config.external_path()`（env → hub.config.yaml → 单点默认）
- **白名单**：只允许两类，且必须写明理由并保持"确有该串"（防止豁免腐化）

## 扫描范围

仓库内 `*.py`，排除运行态/第三方/本地草稿区（`.git`/`.venv`/`node_modules`/`work`/`.tools`/`__pycache__`）。
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_SKIP_DIRS = {
    ".git",
    ".venv",
    ".tools",
    "work",
    "_t1_deps",
    "_t1_venv",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
}

# 用"拼装"而非字面量，避免本文件自己被自己的规则命中
_DRIVE = "[A-Za-z]:"
_SEP = r"[\\/]"
_WORKTREE_NAME = "20260817" + "-Fan-Agent-Momory"  # 拼装：避免本文件被自己的规则命中
_PATTERNS = {
    "个人家目录绝对路径": re.compile(_DRIVE + _SEP + "Users" + _SEP),
    "他机盘符路径（AIwork）": re.compile("D:" + _SEP + "AIwork"),
    "钉死本 worktree 名": re.compile(_WORKTREE_NAME),
}

# 白名单：路径 → 理由（必须仍然含被禁串，否则视为腐化并报错）
_ALLOWED: dict[str, str] = {
    "hub-engine/common/config.py": (
        "external_path() 的**单一**外部项目默认值：仓外项目无法从 __file__ 推导，"
        "散落各处才是病，收敛为一处常量 + env/config 覆盖是正解"
    ),
    "hub-engine/scripts/reclassify.py": (
        "卡片**正文内容**（docstring）里记录的历史路径事实，不是可执行路径；改写反而会让卡片失真"
    ),
}


def _iter_py() -> list[Path]:
    out: list[Path] = []
    for p in _REPO.rglob("*.py"):
        parts = set(p.relative_to(_REPO).parts)
        if parts & _SKIP_DIRS:
            continue
        if p.name == Path(__file__).name and p.parent.name == "tests":
            continue  # 本文件用拼装字符串描述规则，自身不参与扫描
        out.append(p)
    return out


def test_no_hardcoded_personal_paths_in_tracked_python():
    """任何未被白名单豁免的 .py 都不得出现个人/本机绝对路径。"""
    violations: list[str] = []
    for path in _iter_py():
        rel = path.relative_to(_REPO).as_posix()
        if rel in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pat in _PATTERNS.items():
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                violations.append(f"{rel}:{line} [{label}] {m.group(0)}")
    assert not violations, (
        "发现硬编码个人/本机绝对路径（改用 __file__ 自解析 / Path.home() / "
        "common.config.external_path()）：\n  " + "\n  ".join(violations)
    )


def test_whitelist_entries_are_real_and_not_stale():
    """白名单只允许"确有该串"的文件——否则必须删掉豁免（防止豁免腐化）。"""
    for rel, reason in _ALLOWED.items():
        path = _REPO / rel
        assert path.is_file(), f"白名单文件已不存在，请移除豁免：{rel}"
        text = path.read_text(encoding="utf-8", errors="replace")
        assert any(p.search(text) for p in _PATTERNS.values()), (
            f"白名单已失效（文件里不再有被禁串），请移除豁免：{rel}（理由：{reason}）"
        )


def test_guard_covers_the_repo_root_scripts_dir():
    """护栏必须真的扫到仓根 scripts/ 与 hub-engine/scripts/（防止 SKIP_DIRS 写错）。"""
    scanned = {p.relative_to(_REPO).as_posix() for p in _iter_py()}
    assert "scripts/daily_growth.py" in scanned
    assert "hub-engine/scripts/bootstrap_hub.py" in scanned
    assert not any(s.startswith("work/") for s in scanned), "work/ 是本地草稿区，应排除"
