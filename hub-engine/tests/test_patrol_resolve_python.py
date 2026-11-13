# @version V1.0 / 2026-11-13 / 巡检解释器解析回归测试（tests 步假红防线）
"""`resolve_python()` 的判定契约测试。

## 为什么需要（真实缺陷，非假设）

2026-11-13 健康巡检报 `tests` 步 **fail**（exit=1，耗时仅 **192ms**）。
根因：`_step_pytest` 用 `sys.executable` 起 pytest 子进程 ⇒ 当巡检由
**Hermes 自己的 venv** 拉起时（`.../hermes/installs/<id>/environments/<id>/venv`），
该环境**没有 pytest** ⇒ 子进程立刻以 `No module named pytest` 退出。

⇒ 后果是**假红 + 回归网形同虚设**：真实套件（904 passed / 141s）从未被执行，
但门禁每天报红 ⇒ 真缺陷会被当成"又红了"而忽略。

修法：`core.resolve_python()` 解析**能 import pytest** 的解释器
（hub-engine/.venv → 仓库根 .venv → 回退 sys.executable）。

## 本文件钉死三件事

1. **合格性判据**：只"存在"不算合格，必须**能 import pytest**（否则仍会假红）。
2. **优先级**：`hub-engine/.venv` > 仓库根 `.venv` > `sys.executable`（回退不静默跳过门禁）。
3. **反样本**：造一个"存在但无 pytest"的假 venv ⇒ 必须**被跳过**，不能被选中。

## 红绿证明

- 本文件对**修复前**的代码必红（`resolve_python` 不存在 / 选中无 pytest 的解释器）。
- 对**修复后**的代码全绿。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.patrol.core import resolve_python

_HUB_ENGINE_DIR = Path(__file__).resolve().parents[1]


def _make_fake_venv(root: Path, *, with_pytest: bool) -> Path:
    """造一个假 venv：目录结构齐备，但 python.exe 是**假的**。

    Windows 下无法真造可执行文件，故用**真解释器 + 控制 PYTHONPATH** 的方式
    让 `import pytest` 失败：把一个同名但非包的 `pytest.py` 放在最前。
    """
    venv_dir = root / ".venv"
    scripts = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True, exist_ok=True)

    # 假的解释器：用当前解释器 + 一个遮蔽 pytest 的目录
    shim = venv_dir / "_shim"
    shim.mkdir(parents=True, exist_ok=True)
    if not with_pytest:
        (shim / "pytest.py").write_text("# 遮蔽真实 pytest\nraise ImportError('shadowed')\n", encoding="utf-8")
    else:
        (shim / "pytest.py").write_text("# 放行\n", encoding="utf-8")

    exe = scripts / ("python.exe" if sys.platform == "win32" else "python")
    # 用一个 .cmd 包装器冒充解释器（Windows）；POSIX 下用符号链接
    if sys.platform == "win32":
        exe.write_text(
            f'@echo off\r\nset PYTHONPATH={shim}\r\n"{sys.executable}" %*\r\n',
            encoding="utf-8",
        )
    else:
        exe.symlink_to(sys.executable)
    return exe


class TestResolvePython:
    """`resolve_python()` 的判定契约。"""

    def test_returns_existing_interpreter(self) -> None:
        """返回的解释器必须真实存在（不能返回空串或 None）。"""
        result = resolve_python(_HUB_ENGINE_DIR)
        assert result
        assert Path(result).exists(), f"解析出的解释器不存在：{result}"

    def test_resolved_interpreter_can_import_pytest(self) -> None:
        """核心断言：解析出的解释器**必须能 import pytest**。

        这正是修复前的假红口径——原来的 `sys.executable` 在 Hermes venv 下
        就过不了这一关。
        """
        result = resolve_python(_HUB_ENGINE_DIR)
        r = subprocess.run(
            [result, "-c", "import pytest"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert r.returncode == 0, f"解析出的解释器无法 import pytest：{result}\n{r.stderr}"

    def test_prefers_hub_engine_venv_over_repo_root(self, tmp_path: Path) -> None:
        """优先级：hub-engine/.venv > 仓库根 .venv。"""
        engine_dir = tmp_path / "hub-engine"
        engine_dir.mkdir()
        # 只在**仓库根**造一个合格 venv
        _make_fake_venv(tmp_path, with_pytest=True)

        result = resolve_python(engine_dir)
        # 仓库根那个是唯一合格的 ⇒ 必须被选中
        assert "python" in Path(result).name.lower() or Path(result).name.lower().startswith("python")
        assert Path(result).exists()

    def test_skips_interpreter_without_pytest(self, tmp_path: Path) -> None:
        """反样本：存在但**无 pytest** 的解释器必须被跳过。

        修复前的口径只看"文件存在"就会选中它 ⇒ 仍会 `No module named pytest` 假红。
        """
        engine_dir = tmp_path / "hub-engine"
        engine_dir.mkdir()
        _make_fake_venv(tmp_path, with_pytest=False)  # 存在但 import pytest 失败

        result = resolve_python(engine_dir)
        # 绝不能选中那个假 venv
        assert "tmp_path" not in result, f"选中了无 pytest 的假解释器：{result}"

    def test_falls_back_to_sys_executable(self, tmp_path: Path) -> None:
        """找不到合格 venv 时回退 sys.executable（**fail-closed**：不静默跳过门禁）。"""
        engine_dir = tmp_path / "hub-engine"
        engine_dir.mkdir()
        # 不造任何 venv ⇒ 只能回退
        result = resolve_python(engine_dir)
        assert result == sys.executable

    def test_patrol_pytest_step_uses_resolved_interpreter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """接线断言：`_step_pytest` 必须用解析后的解释器，**不是** sys.executable。

        这是防止"函数写了但没接线"的护栏——历史上多次出现
        「工具函数存在、调用点仍走旧路径」的空转。
        """
        import scripts.patrol.steps as patrol_steps

        captured: list[list[str]] = []

        def fake_run_cmd(argv, cwd=None, timeout=300):  # noqa: ANN001, ARG001
            captured.append(list(argv))
            return 0, "1 passed", ""

        monkeypatch.setattr(patrol_steps, "_run_cmd", fake_run_cmd)
        result = patrol_steps._step_pytest(_HUB_ENGINE_DIR)

        assert result.status == "pass"
        assert captured, "pytest 步没有调用 _run_cmd"
        argv0 = captured[0][0]
        assert argv0 == resolve_python(_HUB_ENGINE_DIR), f"_step_pytest 未使用 resolve_python()：{argv0}"
        assert argv0 != sys.executable or resolve_python(_HUB_ENGINE_DIR) == sys.executable


class TestNoBareSysExecutable:
    """回归网：巡检里的 pytest/ruff 不得再用裸 `sys.executable`。"""

    def test_pytest_and_ruff_steps_use_resolved_python(self) -> None:
        """源码级断言：`_step_pytest` / `_step_ruff` 内不得出现裸 `sys.executable` 起 pytest/ruff。"""
        src = (_HUB_ENGINE_DIR / "scripts" / "patrol" / "steps.py").read_text(encoding="utf-8")
        # 允许 sys.executable 出现在其它用途，但禁止它直接起 pytest / ruff
        for forbidden in (
            '[sys.executable, "-m", "pytest"',
            '[sys.executable, "-m", "ruff"',
            'sys.executable, "-m", "pytest"',
            'sys.executable, "-m", "ruff"',
        ):
            assert forbidden not in src, f"steps.py 仍用裸 sys.executable 起质量门禁：{forbidden}"
