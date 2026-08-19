"""vector_scale_bench 性能门禁（建议 3）单测。

用子进程跑脚本的 --single --fail-above 单点门禁模式，验证退出码：
- 耗时超阈值 → 退出码 4（性能门禁未通过）
- 阈值足够宽松 → 退出码 0
隔离库 work/bench_scale（gitignored），不触碰真实中枢。
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vector_scale_bench.py"


def _run(single: int, fail_above: float | None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--single", str(single), "--repeat", "3"]
    if fail_above is not None:
        cmd += ["--fail-above", str(fail_above)]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_single_mode_exit_zero_with_loose_gate():
    """单点模式 + 极宽松阈值 → 退出码 0（门禁放行）"""
    r = _run(50, fail_above=100_000.0)
    assert r.returncode == 0, r.stderr
    assert "单点 size=50" in r.stdout


def test_single_mode_gate_fails_on_tight_threshold():
    """单点模式 + 极紧阈值 → 退出码 4（性能门禁未通过）"""
    r = _run(50, fail_above=0.000001)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "性能门禁失败" in r.stdout


def test_single_mode_without_gate_exit_zero():
    """单点模式但不设 fail-above → 只测不拦，退出码 0"""
    r = _run(50, fail_above=None)
    assert r.returncode == 0, r.stderr
    assert "单点 size=50" in r.stdout


def test_full_curve_path_still_exits_zero():
    """不带 --single 走全曲线（多规模）仍退出 0，门禁参数不干扰原路径"""
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--sizes",
        "50",
        "100",
        "--repeat",
        "3",
        "--fail-above",
        "999999",
    ]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert r.returncode == 0, r.stderr
    assert "单点" not in r.stdout  # 非单点模式
    assert "50" in r.stdout and "100" in r.stdout
