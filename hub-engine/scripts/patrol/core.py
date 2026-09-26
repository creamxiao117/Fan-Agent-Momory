# @version V3.1 / 2026-09-25 / pi / 巡检核心层（数据模型 + 步骤执行器）
"""patrol.core — 巡检的数据模型与执行器。

从 `patrol_runner.py`（1,597 行）拆出：**不依赖任何步骤实现**，被 steps/report/runner 共用。

- `StepResult` / `StageResult` / `PatrolReport`：报告数据模型（`to_dict` 供 --json 用）
- `_run_step(name, func, ...)`：步骤包装器（计时、异常兜底、状态归一）
- `_run_cmd(...)`：子进程执行器（退出码/超时/输出截断口径的统一入口）
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import Path

_HUB_ENGINE_DIR = Path(__file__).resolve().parents[2]
if str(_HUB_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE_DIR))

_LOCAL_TZ = timezone(timedelta(hours=+8))


@dataclass
class StepResult:
    """单步执行结果。"""

    name: str
    stage: str
    status: str  # pass / fail / skip / warn
    exit_code: int = 0
    output: str = ""
    duration_ms: float = 0.0
    error: str | None = None

    # 用于自动修复层的附加元信息（可选）
    meta: dict = field(default_factory=dict)


@dataclass
class StageResult:
    """阶段执行结果。"""

    name: str
    steps: list[StepResult] = field(default_factory=list)
    skipped: bool = False

    @property
    def has_failures(self) -> bool:
        return any(s.status == "fail" for s in self.steps)

    @property
    def has_warnings(self) -> bool:
        return any(s.status == "warn" for s in self.steps)


@dataclass
class PatrolReport:
    """完整巡检报告。"""

    hub_root: str = ""
    generated_at: str = ""
    stages: list[StageResult] = field(default_factory=list)
    llm_available: bool = True  # v3: 原 ollama_available
    overall_exit_code: int = 0
    snapshot: dict = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    auto_fix_results: dict = field(default_factory=dict)  # v3 新增

    def to_dict(self) -> dict:
        return {
            "hub_root": self.hub_root,
            "generated_at": self.generated_at,
            "llm_available": self.llm_available,
            "overall_exit_code": self.overall_exit_code,
            "stages": [
                {
                    "name": s.name,
                    "skipped": s.skipped,
                    "steps": [
                        {
                            "name": st.name,
                            "stage": st.stage,
                            "status": st.status,
                            "exit_code": st.exit_code,
                            "duration_ms": round(st.duration_ms, 1),
                            "error": st.error,
                            "meta": st.meta,
                        }
                        for st in s.steps
                    ],
                }
                for s in self.stages
            ],
            "snapshot": self.snapshot,
            "alerts": self.alerts,
            "suggestions": self.suggestions,
            "auto_fix_results": self.auto_fix_results,
        }


def _run_step(
    name: str,
    stage: str,
    fn: Callable[[], StepResult],
    *,
    pre_check: Callable[[], bool] | None = None,
) -> StepResult:
    """执行单个步骤，带前置检查。"""
    if pre_check and not pre_check():
        return StepResult(
            name=name,
            stage=stage,
            status="skip",
            output="前置检查未通过，跳过",
        )
    try:
        t0 = time.time()
        result = fn()
        result.name = name
        result.stage = stage
        result.duration_ms = (time.time() - t0) * 1000
        return result
    except Exception as e:
        return StepResult(
            name=name,
            stage=stage,
            status="fail",
            exit_code=999,
            error=str(e),
        )


def _run_cmd(
    argv: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """运行外部命令，返回 (exit_code, stdout, stderr)。"""
    try:
        r = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"超时 ({timeout}s)"
    except (subprocess.SubprocessError, OSError) as e:
        return 127, "", str(e)
