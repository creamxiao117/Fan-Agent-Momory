"""patrol CLI 入口 + 拆包后的向后兼容 re-export 守护。

背景（2026-09-25 拆 `steps/` 包时实测踩到）：把 `main()` 搬进新文件时漏掉了
`if __name__ == "__main__"` 块 ⇒ `python -m scripts.patrol_runner` **静默 exit 0 什么都不做**
（定时任务的"假绿"）。契约测试只调函数，测不出入口缺失 —— 本文件把这个洞钉死。
"""

import subprocess
import sys
from pathlib import Path

import scripts.patrol.core as patrol_core
import scripts.patrol_runner as patrol

ENGINE = Path(__file__).resolve().parents[1]


def test_module_cli_help_prints_usage():
    """`python -m scripts.patrol_runner --help` 必须真打印用法（守护 __main__ 入口）"""
    r = subprocess.run(
        [sys.executable, "-m", "scripts.patrol_runner", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ENGINE,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[:300]
    assert "usage" in (r.stdout + r.stderr).lower()
    assert "dry-run" in r.stdout  # 关键参数在位


def test_runner_reexports_every_public_name():
    """拆包后旧的调用面（`patrol_runner.<name>`）必须仍然可用"""
    missing = [n for n in patrol.__all__ if not hasattr(patrol, n)]
    assert missing == []


def test_reexports_are_the_same_objects():
    """re-export 必须是**同一个对象**（不是复制），否则 monkeypatch 打不到真实位置"""
    assert patrol.StepResult is patrol_core.StepResult
    assert patrol.PatrolReport is patrol_core.PatrolReport
    assert patrol._run_cmd is patrol_core._run_cmd
    assert patrol._run_step is patrol_core._run_step


def test_run_patrol_and_main_are_callable():
    assert callable(patrol.run_patrol)
    assert callable(patrol.main)
