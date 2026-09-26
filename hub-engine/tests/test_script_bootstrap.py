"""护栏：仓库内脚本必须在 import 项目包之前自己引导 sys.path（防 2026-09-26 那类回归）。

背景：`hub-engine/scripts/*.py` 既可能被
  ① `cd hub-engine && python -m scripts.x` 调用（cwd 在 hub-engine，`common` 可导入），
  ② 也可能被外部调度器（Hermes cron / 计划任务）用**绝对路径**直接跑（cwd 任意）。
第二种情况下，若脚本没有 `sys.path.insert(hub-engine)` 就直接 `import common.*`，
就会 `ModuleNotFoundError: No module named 'common'` —— 2026-09-26 06:00 的
「T15-6工具每日编排」就是这么挂的（P1-c 加入 `from common.config import external_path` 时漏了引导）。
"""

import ast
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
SCRIPTS = ENGINE / "scripts"
PROJECT_PKGS = ("common", "tools", "commands")


def _module_level_project_imports(tree: ast.Module) -> list[int]:
    """模块级 `import common.*` / `from tools.x import y` 的行号"""
    lines: list[int] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in PROJECT_PKGS:
                lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in PROJECT_PKGS:
                    lines.append(node.lineno)
    return lines


def _sys_path_bootstrap_line(tree: ast.Module) -> int | None:
    """返回第一处 `sys.path.insert(...)` 的行号（模块级）"""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "insert"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "path"
        ):
            return node.lineno
    return None


def test_scripts_importing_project_packages_bootstrap_path():
    offenders: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        imports = _module_level_project_imports(tree)
        if not imports:
            continue
        bootstrap = _sys_path_bootstrap_line(tree)
        if bootstrap is None or bootstrap > min(imports):
            offenders.append(
                f"{path.relative_to(ENGINE)}（首次 import 在第 {min(imports)} 行，引导在第 {bootstrap} 行）"
            )
    assert offenders == [], (
        "以下脚本在 import 项目包之前没有引导 sys.path（外部调度器用绝对路径跑会 ModuleNotFoundError）：\n  "
        + "\n  ".join(offenders)
    )


def test_orchestrator_runs_from_foreign_cwd(tmp_path):
    """端到端：以「任意 cwd + 绝对路径」跑一次 hub_orchestrator（模拟 Hermes cron）"""
    script = SCRIPTS / "hub_orchestrator.py"
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,  # 关键：cwd 不是 hub-engine
        timeout=120,
    )
    assert r.returncode == 0, f"stdout={r.stdout[:300]} stderr={r.stderr[:500]}"
    assert "usage" in (r.stdout + r.stderr).lower()
