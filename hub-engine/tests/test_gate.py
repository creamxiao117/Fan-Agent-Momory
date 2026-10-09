# @version V1.0 / 2026-10-09 / pi / 体检回归：`hub gate` 步骤根目录与用例收集
"""`commands.gate.cmd_gate` 单测——**先证红再修**的落点。

回归背景（2026-10-09 中枢体检发现）：
    `engine_dir` 曾误取 `Path(__file__).parent`（= `hub-engine/commands`），导致
      · pytest 在 `commands/` 下**收集 0 个用例**（exit=5）——门禁"绿"其实从未跑过测试；
      · ruff 只扫 `commands/`，漏掉 `tools/` `common/` `scripts/`；
      · `engine_dir/scripts/vector_bench.py` 解析成不存在的 `commands/scripts/...`（exit=2）。
本文件把"三步都必须在 hub-engine 根、且脚本路径必须真实存在"固化为回归。
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace

from commands.gate import cmd_gate

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _args(**overrides) -> SimpleNamespace:
    base = dict(
        root=str(ENGINE_ROOT.parent / "AgentMemoryHub"),
        fail_below=None,
        skip_pytest=False,
        skip_ruff=False,
        skip_vector=False,
        keep_going=True,
        timeout=600,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patched(monkeypatch, calls: list) -> None:
    monkeypatch.setattr(
        "tools.lint.lint",
        lambda root: {"orphans": [], "ghosts": [], "stale": [], "invalid": 0},
    )

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_gate_steps_run_from_engine_root(monkeypatch):
    """三步子进程的 cwd 都必须是 hub-engine 根，而不是 commands/。"""
    calls: list = []
    _patched(monkeypatch, calls)

    assert cmd_gate(_args()) == 0
    assert calls, "三步都未被调用"
    for argv, kwargs in calls:
        assert Path(kwargs["cwd"]) == ENGINE_ROOT, argv


def test_gate_vector_bench_path_exists(monkeypatch):
    """vector_bench.py 必须在 cwd 下真实存在（旧路径指向 commands/scripts/，不存在）。"""
    calls: list = []
    _patched(monkeypatch, calls)

    cmd_gate(_args())
    argv, kwargs = next((a, k) for a, k in calls if "vector_bench" in " ".join(a))
    script = Path(argv[1])
    assert script.name == "vector_bench.py"
    assert script.is_file()


def test_gate_pytest_collects_tests(monkeypatch):
    """pytest 步骤必须能在其 cwd 下看到 tests/（收集 0 个用例 = 假绿，必须回归可见）。"""
    calls: list = []
    _patched(monkeypatch, calls)

    cmd_gate(_args())
    argv, kwargs = next((a, k) for a, k in calls if "pytest" in a)
    assert argv[1:] == ["-m", "pytest", "-q"]
    assert (Path(kwargs["cwd"]) / "tests").is_dir()
    assert (Path(kwargs["cwd"]) / "tests" / "test_gate.py").is_file()


def test_gate_resolves_relative_root_for_child_processes(monkeypatch, tmp_path):
    """回归（2026-10-09 体检第二条）：`--root` 传相对路径时，子进程拿到的必须是
    **绝对路径**。否则子进程在 hub-engine cwd 下找不到中枢 ⇒ vector_bench 静默
    0% 且 exit 0（假绿）。"""
    calls: list = []
    _patched(monkeypatch, calls)
    monkeypatch.chdir(tmp_path)
    hub = tmp_path / "AgentMemoryHub"
    hub.mkdir()

    cmd_gate(_args(root="AgentMemoryHub"))
    argv, _ = next((a, k) for a, k in calls if "vector_bench" in " ".join(a))
    passed_root = Path(argv[-1])
    assert passed_root.is_absolute(), argv
    assert passed_root == hub.resolve()


def test_vector_bench_refuses_missing_hub_root(tmp_path):
    """回归（2026-10-09 体检）：`--real` 指向不存在/非中枢路径时必须 127，
    不得输出「0% 但 exit 0」（那会让 vector_regression 步变成空转的假绿）。"""
    from scripts.vector_bench import _run_real

    assert _run_real(tmp_path / "nope", 3, None) == 127
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _run_real(empty, 3, None) == 127
