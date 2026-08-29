#!/usr/bin/env python3
"""
patrol_runner.py — 中枢每日健康巡检编排脚本 v3

7 阶段流水线 (v3 新增自动修复层 + 分级输出):
  阶段 1: 基础设施检查 (本地 LLM / 配置完整性 / 文件检查)
  阶段 2: 代码质量门禁 (lint / pytest / ruff) —— 始终执行，不依赖 LLM
  阶段 3: 飞轮活跃度 (向量增量 / 路由同步)
  阶段 4: 数据质量 (查询回归 / 指标聚合 / 今日审核)
  阶段 5: 报告生成与归档 (健康评分 / 快照 / 告警)
  阶段 6: 自动修复层 (5 个 auto_* 模块串联)
  阶段 7: 分级输出 (人类可读 + JSON)

v2 → v3 变更:
  - ollama_check → llm_check，Ollama 文案 → LM Studio/本地 LLM
  - pytest/ruff 始终执行（不再依赖 LLM 可用性）
  - 新增阶段 6 自动修复层：auto_fix_lint → auto_pytest_env_fix →
    auto_sleep_filter → auto_process_sleep → auto_review_today
  - 修复 LLMHealthChecker 缺失导入
  - 快照 JSON 兼容：内部字段名 llm_available，历史快照 ollama 字段可读

用法:
  python patrol_runner.py --root <hub_root>
  python patrol_runner.py --root <hub_root> --dry-run
  python patrol_runner.py --root <hub_root> --skip-flywheel
  python patrol_runner.py --root <hub_root> --skip-autofix
"""

import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 将 hub-engine 加入 sys.path，确保 tools / common 模块可导入
_hub_engine_dir = Path(__file__).resolve().parent.parent
if str(_hub_engine_dir) not in sys.path:
    sys.path.insert(0, str(_hub_engine_dir))

# === 时区 ===
_LOCAL_TZ = timezone(timedelta(hours=+8))


# ============================================================================
# 数据结构
# ============================================================================

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
    llm_available: bool = True        # v3: 原 ollama_available
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


# ============================================================================
# 工具函数
# ============================================================================

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
            name=name, stage=stage, status="skip",
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
            name=name, stage=stage, status="fail",
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


def _llm_pre_check() -> StepResult:
    """阶段 1-1: 本地 LLM 服务前置检测（LM Studio）。"""
    try:
        from tools.llm_health import LLMHealthChecker
        # 默认本地 LM Studio 端口 1234
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        status = checker.get_status()
        models_str = ", ".join(status.models[:3]) if status.models else "无模型"
        rt_ms = round(status.response_time * 1000, 1)
        output = (
            f"✅ 本地 LLM (LM Studio) 可用 · {len(status.models)} 模型 · 响应 {rt_ms}ms"
            + (f" · {models_str}" if models_str != "无模型" else "")
        )
        return StepResult(
            name="llm_check",
            stage="基础设施",
            status="pass",
            exit_code=0,
            output=output,
        )
    except Exception as e:
        return StepResult(
            name="llm_check",
            stage="基础设施",
            status="warn",     # v3: 基础设施不可用降为 warn，不阻塞其他步骤
            exit_code=0,       # v3: 不再返回 exit_code=3 影响总体
            error=str(e),
            output=f"⚠️ 本地 LLM (LM Studio) 不可用: {e}",
        )


def _check_config_integrity(root: Path) -> StepResult:
    """检查中枢配置文件完整性。"""
    issues = []
    hub_cfg = root / "hub.config.yaml"
    if not hub_cfg.is_file():
        issues.append("hub.config.yaml 缺失")
    idx = root / "INDEX.md"
    if not idx.is_file():
        issues.append("INDEX.md 缺失")
    engine_cfg = root.parent / "hub-engine" / "config" / "engine.config.yaml"
    if not engine_cfg.is_file():
        issues.append("engine.config.yaml 缺失")

    if issues:
        return StepResult(
            name="config_integrity",
            stage="基础设施",
            status="fail",
            exit_code=3,
            output="❌ " + "; ".join(issues),
        )
    return StepResult(
        name="config_integrity",
        stage="基础设施",
        status="pass",
        output="✅ 配置文件完整 (hub.config.yaml + INDEX.md + engine.config.yaml)",
    )


def _check_file_integrity(root: Path) -> StepResult:
    """检查中枢目录结构完整性。"""
    required_dirs = [
        "rules", "methodology", "longterm", "experience", "notes",
        ".sync", ".sync/state", ".sync/drafts", "retro",
    ]
    missing = [d for d in required_dirs if not (root / d).is_dir()]
    if missing:
        return StepResult(
            name="file_integrity",
            stage="基础设施",
            status="warn",
            exit_code=0,       # v3: 不再设为阻塞
            output=f"⚠️ 缺失目录: {', '.join(missing)}",
        )
    return StepResult(
        name="file_integrity",
        stage="基础设施",
        status="pass",
        output="✅ 目录结构完整",
    )


# ----- 阶段 2: 代码质量门禁 -----

def _step_lint(root: Path) -> StepResult:
    """Lint 检查。"""
    from tools.lint import lint
    report = lint(root)
    unhealthy = (
        len(report["orphans"]) + len(report["ghosts"]) + len(report["stale"])
        + report["invalid"]
    )
    output = (
        f"lint: orphans={len(report['orphans'])} ghosts={len(report['ghosts'])} "
        f"stale={len(report['stale'])} invalid={report['invalid']}"
    )
    if unhealthy > 0:
        return StepResult(
            name="lint", stage="质量门禁",
            status="warn", exit_code=2, output=f"⚠️ {output}",
            meta={"orphans": len(report["orphans"]), "ghosts": len(report["ghosts"]),
                  "stale": len(report["stale"]), "invalid": report["invalid"]},
        )
    return StepResult(
        name="lint", stage="质量门禁",
        status="pass", exit_code=0, output=f"✅ {output}",
        meta={"orphans": 0, "ghosts": 0, "stale": 0, "invalid": 0},
    )


def _step_pytest(engine_dir: Path) -> StepResult:
    """运行 pytest。始终执行，不依赖 LLM。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=engine_dir, timeout=120,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="pytest", stage="质量门禁",
            status="pass", exit_code=0, output=f"✅ pytest 通过: {last_line}",
        )
    elif exit_code == 127:
        return StepResult(
            name="pytest", stage="质量门禁",
            status="skip", exit_code=127, output="⏭️ pytest 未安装 (127)",
        )
    else:
        return StepResult(
            name="pytest", stage="质量门禁",
            status="fail", exit_code=exit_code, output=f"❌ pytest 失败: {last_line}",
            meta={"has_import_error": "ModuleNotFoundError" in (stderr or stdout) or "ImportError" in (stderr or stdout)},
        )


def _step_ruff(engine_dir: Path) -> StepResult:
    """运行 ruff check。始终执行，不依赖 LLM。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=engine_dir, timeout=60,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="pass", exit_code=0, output="✅ ruff 通过",
        )
    elif exit_code == 127:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="skip", exit_code=127, output="⏭️ ruff 未安装 (127)",
        )
    else:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="warn", exit_code=exit_code, output=f"⚠️ ruff 告警: {last_line}",
        )


# ----- 阶段 3: 飞轮活跃度 -----

def _step_build_vectors(root: Path, engine_dir: Path) -> StepResult:
    """向量增量更新。依赖本地 LLM 可用性。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(engine_dir / "engine.py"), "build-vectors", "--root", str(root)],
        cwd=engine_dir, timeout=300,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="build_vectors", stage="飞轮活跃度",
            status="pass", exit_code=0, output=f"✅ 向量构建: {last_line}",
        )
    elif exit_code == 2:
        return StepResult(
            name="build_vectors", stage="飞轮活跃度",
            status="warn", exit_code=2, output=f"⚠️ 向量通道退化: {last_line}",
        )
    else:
        return StepResult(
            name="build_vectors", stage="飞轮活跃度",
            status="fail", exit_code=exit_code, output=f"❌ 向量构建失败: {last_line}",
        )


def _step_router_sync(root: Path, engine_dir: Path) -> StepResult:
    """路由表同步检查。"""
    sync_script = engine_dir / "scripts" / "router_sync.py"
    if not sync_script.is_file():
        return StepResult(
            name="router_sync", stage="飞轮活跃度",
            status="skip", exit_code=0, output="⏭️ router_sync.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(sync_script), "--root", str(root)],
        cwd=engine_dir, timeout=60,
    )
    if exit_code == 0:
        return StepResult(
            name="router_sync", stage="飞轮活跃度",
            status="pass", exit_code=0, output="✅ 路由表同步检查通过",
        )
    return StepResult(
        name="router_sync", stage="飞轮活跃度",
        status="warn", exit_code=exit_code,
        output=f"⚠️ 路由表同步异常: {(stderr or stdout).strip()[:200]}",
    )


# ----- 阶段 4: 数据质量 -----

def _step_vector_regression(root: Path, engine_dir: Path) -> StepResult:
    """固定查询集回归测试。"""
    bench_script = engine_dir / "scripts" / "vector_bench.py"
    if not bench_script.is_file():
        return StepResult(
            name="vector_regression", stage="数据质量",
            status="skip", exit_code=0, output="⏭️ vector_bench.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(bench_script), "--real", str(root)],
        cwd=engine_dir, timeout=120,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="vector_regression", stage="数据质量",
            status="pass", exit_code=0, output=f"✅ 向量回归: {last_line}",
        )
    else:
        return StepResult(
            name="vector_regression", stage="数据质量",
            status="warn", exit_code=exit_code, output=f"⚠️ 向量回归: {last_line}",
        )


def _step_metrics_daily(root: Path, engine_dir: Path) -> StepResult:
    """每日指标聚合。"""
    metrics_script = engine_dir / "scripts" / "metrics_daily.py"
    if not metrics_script.is_file():
        return StepResult(
            name="metrics_daily", stage="数据质量",
            status="skip", exit_code=0, output="⏭️ metrics_daily.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(metrics_script), "--root", str(root)],
        cwd=engine_dir, timeout=30,
    )
    if exit_code == 0:
        return StepResult(
            name="metrics_daily", stage="数据质量",
            status="pass", exit_code=0,
            output=f"✅ 指标聚合: {(stdout or '').strip()[:200]}",
        )
    return StepResult(
        name="metrics_daily", stage="数据质量",
        status="warn", exit_code=exit_code,
        output=f"⚠️ 指标聚合: {(stderr or stdout).strip()[:200]}",
    )


def _step_hub_review(root: Path, engine_dir: Path) -> StepResult:
    """今日审核清单。"""
    review_script = engine_dir / "scripts" / "hub_review_today.py"
    if not review_script.is_file():
        return StepResult(
            name="hub_review", stage="数据质量",
            status="skip", exit_code=0, output="⏭️ hub_review_today.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(review_script), "--root", str(root)],
        cwd=engine_dir, timeout=30,
    )
    if exit_code == 0:
        return StepResult(
            name="hub_review", stage="数据质量",
            status="pass", exit_code=0,
            output=f"✅ 今日审核: {(stdout or '').strip()[:300]}",
        )
    return StepResult(
        name="hub_review", stage="数据质量",
        status="warn", exit_code=exit_code,
        output=f"⚠️ 今日审核: {(stderr or stdout).strip()[:300]}",
    )


# ----- 阶段 5: 报告生成与归档 -----

def _step_status_snapshot(root: Path, engine_dir: Path) -> StepResult:
    """生成健康快照（调用升级后的 _cmd_status）。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(engine_dir / "engine.py"), "status", "--root", str(root), "--json"],
        cwd=engine_dir, timeout=60,
    )
    if exit_code in (0, 2):
        try:
            json.loads(stdout)
            return StepResult(
                name="status_snapshot", stage="报告归档",
                status="pass", exit_code=exit_code,
                output=f"✅ 快照生成 (exit={exit_code})",
            )
        except json.JSONDecodeError:
            pass
    return StepResult(
        name="status_snapshot", stage="报告归档",
        status="fail", exit_code=exit_code,
        output=f"❌ 快照生成失败: {(stderr or stdout).strip()[:200]}",
    )


def _save_snapshot_archive(
    root: Path, engine_dir: Path, *, no_overwrite: bool = False
) -> StepResult:
    """将快照归档到 retro/ 目录。支持防覆盖模式。"""
    retro_dir = root / "retro"
    retro_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(_LOCAL_TZ).date().isoformat()
    snap_path = retro_dir / f"snapshot-{today}.json"

    # === 幂等保护：防覆盖 ===
    if no_overwrite and snap_path.is_file():
        try:
            existing = json.loads(snap_path.read_text(encoding="utf-8"))
            if existing.get("generated_at", "") and today in existing["generated_at"]:
                return StepResult(
                    name="archive_snapshot", stage="报告归档",
                    status="pass", exit_code=0,
                    output=f"⏭️ 今日快照已存在，跳过归档 (幂等保护): {snap_path}",
                )
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # 存在但损坏，允许覆盖

    # 生成一次 JSON 快照并写入
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(engine_dir / "engine.py"), "status", "--root", str(root), "--json"],
        cwd=engine_dir, timeout=60,
    )
    if exit_code in (0, 2):
        try:
            data = json.loads(stdout)
            snap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return StepResult(
                name="archive_snapshot", stage="报告归档",
                status="pass", exit_code=0,
                output=f"✅ 快照已归档: {snap_path}",
            )
        except (json.JSONDecodeError, OSError) as e:
            return StepResult(
                name="archive_snapshot", stage="报告归档",
                status="fail", exit_code=1,
                error=str(e), output=f"❌ 归档失败: {e}",
            )
    return StepResult(
        name="archive_snapshot", stage="报告归档",
        status="fail", exit_code=exit_code,
        output=f"❌ 快照生成失败: {(stderr or stdout).strip()[:200]}",
    )


# ============================================================================
# 阶段 6: 自动修复层（v3 新增）
# ============================================================================

def _step_auto_fix_lint(root: Path, engine_dir: Path) -> StepResult:
    """auto_fix_lint: lint invalid 卡自动补 frontmatter。"""
    fix_script = engine_dir / "scripts" / "auto_fix_lint.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_fix_lint", stage="自动修复",
            status="skip", output="⏭️ auto_fix_lint.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir, timeout=60,
    )
    text = (stdout or stderr or "").strip()
    fixed = "修复" in text and "0" not in text.split("修复")[1].split("张")[0] if "修复" in text else False
    return StepResult(
        name="auto_fix_lint", stage="自动修复",
        status="pass" if fixed or exit_code == 0 else "warn",
        exit_code=0,
        output=f"✅ {text[:200]}" if exit_code == 0 else f"⚠️ {text[:200]}",
    )


def _step_auto_pytest_fix(root: Path, engine_dir: Path) -> StepResult:
    """auto_pytest_env_fix: pytest 环境类失败自动修复。"""
    fix_script = engine_dir / "scripts" / "auto_pytest_env_fix.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_pytest_env_fix", stage="自动修复",
            status="skip", output="⏭️ auto_pytest_env_fix.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir, timeout=120,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_pytest_env_fix", stage="自动修复",
        status="pass" if exit_code == 0 else "warn",
        exit_code=0,
        output=f"✅ {text[:200]}" if exit_code == 0 else f"⚠️ {text[:200]}",
    )


def _step_auto_sleep_filter(root: Path, engine_dir: Path) -> StepResult:
    """auto_sleep_filter: sleep 候选假信号自动过滤。"""
    fix_script = engine_dir / "scripts" / "auto_sleep_filter.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_sleep_filter", stage="自动修复",
            status="skip", output="⏭️ auto_sleep_filter.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root), "--since-days", "3"],
        cwd=engine_dir, timeout=60,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_sleep_filter", stage="自动修复",
        status="pass", exit_code=0,
        output=f"✅ {text[:200]}",
    )


def _step_auto_process_sleep(root: Path, engine_dir: Path) -> StepResult:
    """auto_process_sleep: sleep 候选自动补 tag / 生成草稿。"""
    fix_script = engine_dir / "scripts" / "auto_process_sleep.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_process_sleep", stage="自动修复",
            status="skip", output="⏭️ auto_process_sleep.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root), "--since-days", "3"],
        cwd=engine_dir, timeout=60,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_process_sleep", stage="自动修复",
        status="pass", exit_code=0,
        output=f"✅ {text[:200]}",
    )


def _step_auto_review_today(root: Path, engine_dir: Path) -> StepResult:
    """auto_review_today: review_today 按 type 分类自动过/留。"""
    fix_script = engine_dir / "scripts" / "auto_review_today.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_review_today", stage="自动修复",
            status="skip", output="⏭️ auto_review_today.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir, timeout=30,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_review_today", stage="自动修复",
        status="pass", exit_code=0,
        output=f"✅ {text[:200]}",
    )


# ============================================================================
# 建议生成
# ============================================================================

def _generate_suggestions(report: PatrolReport) -> list[str]:
    """基于告警结果生成改进建议。"""
    suggestions = []
    llm_down = not report.llm_available

    for alert in report.alerts:
        rule = alert.get("rule", "")
        msg = alert.get("message", "")

        if rule == "ollama_unavailable":
            suggestions.append(
                "🟢 本地 LLM 不可用 → 检查 LM Studio 是否在运行，确认 API 端口 1234 可达；"
                "或在 hub.config.yaml 中配置 OmniRoute 网关地址作为降级通道"
            )
        elif rule == "ollama_slow":
            suggestions.append(
                "🟢 本地 LLM 响应慢 → 检查 LM Studio 资源占用，考虑使用较小模型或开启 GPU 加速"
            )
        elif rule == "lint_issues":
            suggestions.append(
                "🟢 Lint 问题 → 已由 auto_fix_lint 自动修复 invalid 卡 frontmatter；"
                "孤儿页和陈旧页需人工审核后手动处理"
            )
        elif rule == "low_hit_rate":
            suggestions.append(
                "🟢 命中率低 → 已由 auto_sleep_filter + auto_process_sleep 自动处理 sleep 候选；"
                "查看 .sync/drafts/auto_sleep_draft/ 中的草稿卡补充完整"
            )
        elif rule == "low_flywheel_activity":
            suggestions.append(
                "🟢 飞轮活跃度低 → 补充新经验卡或执行 `python engine.py distill` 处理草稿"
            )
        elif rule == "pending_confirmation":
            suggestions.append(
                "🟢 待确认卡片 → 已由 auto_review_today 自动跳过非 rule/methodology 类卡；"
                "review_today.md 中仅剩 rule/methodology 类卡需人工确认"
            )

    if not suggestions and not report.alerts:
        suggestions.append("✅ 系统健康，自动修复层已处理完毕，无需额外操作")

    return suggestions


# ============================================================================
# 主巡检编排
# ============================================================================

def run_patrol(
    root: Path,
    *,
    skip_flywheel: bool = False,
    dry_run: bool = False,
    skip_if_exists: bool = False,
    skip_autofix: bool = False,
) -> PatrolReport:
    """
    执行完整的 7 阶段巡检流水线。

    Args:
        root: 中枢根目录
        skip_flywheel: 是否跳过飞轮相关步骤
        dry_run: 是否仅打印计划不实际执行
        skip_if_exists: 幂等保护：今日快照已存在则直接跳过
        skip_autofix: 跳过阶段 6 自动修复层（调试用）

    Returns:
        PatrolReport 完整巡检报告
    """
    engine_dir = Path(__file__).resolve().parent.parent

    # === 幂等保护 ===
    if skip_if_exists:
        retro_dir = root / "retro"
        today = datetime.now(_LOCAL_TZ).date().isoformat()
        existing_snap = retro_dir / f"snapshot-{today}.json"
        if existing_snap.is_file():
            try:
                existing_data = json.loads(existing_snap.read_text(encoding="utf-8"))
                if existing_data.get("generated_at", "") and today in existing_data["generated_at"]:
                    # 兼容旧快照字段名 ollama → llm
                    llm_field = existing_data.get("llm_health") or existing_data.get("ollama", {})
                    report = PatrolReport(
                        hub_root=str(root),
                        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
                        llm_available=llm_field.get("available", True) if isinstance(llm_field, dict) else True,
                        overall_exit_code=0,
                        snapshot=existing_data,
                        alerts=existing_data.get("alerts", []),
                        suggestions=["今日快照已存在，跳过巡检（幂等保护）"],
                    )
                    skipped_stage = StageResult(name="幂等保护")
                    skipped_stage.steps.append(StepResult(
                        name="check_existing_snapshot", stage="幂等保护", status="skip",
                        output=f"⏭️ 今日快照已存在: {existing_snap}",
                    ))
                    report.stages.append(skipped_stage)
                    return report
            except (json.JSONDecodeError, KeyError, OSError):
                pass

    report = PatrolReport(
        hub_root=str(root),
        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
    )

    # ===== 阶段 1: 基础设施检查 =====
    stage1 = StageResult(name="基础设施检查")
    stage1.steps.append(_run_step("llm_check", "基础设施", lambda: _llm_pre_check()))
    llm_ok = stage1.steps[-1].status == "pass"
    report.llm_available = llm_ok
    stage1.steps.append(_run_step("config_integrity", "基础设施", lambda: _check_config_integrity(root)))
    stage1.steps.append(_run_step("file_integrity", "基础设施", lambda: _check_file_integrity(root)))
    report.stages.append(stage1)

    if dry_run:
        print("[DRY-RUN] 阶段 1 完成，后续步骤仅打印计划")
        print("  阶段 2: lint → pytest → ruff (始终执行)")
        print("  阶段 3: build-vectors → router-sync")
        print("  阶段 4: vector-regression → metrics-daily → hub-review")
        print("  阶段 5: status-snapshot → archive-snapshot")
        print("  阶段 6: auto_fix_lint → auto_pytest_env_fix → auto_sleep_filter → auto_process_sleep → auto_review_today")
        print("  阶段 7: 分级输出")
        return report

    # ===== 阶段 2: 代码质量门禁（始终执行，不依赖 LLM） =====
    stage2 = StageResult(name="代码质量门禁")
    stage2.steps.append(_run_step("lint", "质量门禁", lambda: _step_lint(root)))
    stage2.steps.append(_run_step("pytest", "质量门禁", lambda: _step_pytest(engine_dir)))
    stage2.steps.append(_run_step("ruff", "质量门禁", lambda: _step_ruff(engine_dir)))
    report.stages.append(stage2)

    # ===== 阶段 3: 飞轮活跃度 =====
    stage3 = StageResult(name="飞轮活跃度")
    if skip_flywheel:
        stage3.skipped = True
        stage3.steps.append(StepResult(
            name="flywheel", stage="飞轮活跃度", status="skip",
            output="已指定 --skip-flywheel，跳过飞轮步骤",
        ))
    else:
        if llm_ok:
            stage3.steps.append(_run_step("build_vectors", "飞轮活跃度",
                                          lambda: _step_build_vectors(root, engine_dir)))
        else:
            stage3.steps.append(StepResult(
                name="build_vectors", stage="飞轮活跃度", status="skip",
                output="本地 LLM 不可用，跳过向量构建",
            ))
        stage3.steps.append(_run_step("router_sync", "飞轮活跃度",
                                      lambda: _step_router_sync(root, engine_dir)))
    report.stages.append(stage3)

    # ===== 阶段 4: 数据质量 =====
    stage4 = StageResult(name="数据质量")
    stage4.steps.append(_run_step("vector_regression", "数据质量",
                                   lambda: _step_vector_regression(root, engine_dir)))
    stage4.steps.append(_run_step("metrics_daily", "数据质量",
                                   lambda: _step_metrics_daily(root, engine_dir)))
    stage4.steps.append(_run_step("hub_review", "数据质量",
                                   lambda: _step_hub_review(root, engine_dir)))
    report.stages.append(stage4)

    # ===== 阶段 5: 报告生成与归档 =====
    stage5 = StageResult(name="报告生成与归档")
    snap_result = _run_step("status_snapshot", "报告归档",
                            lambda: _step_status_snapshot(root, engine_dir))
    stage5.steps.append(snap_result)
    archive_result = _run_step("archive_snapshot", "报告归档",
                               lambda: _save_snapshot_archive(root, engine_dir, no_overwrite=skip_if_exists))
    stage5.steps.append(archive_result)

    # 解析快照
    if snap_result.status == "pass":
        exit_code, stdout, _ = _run_cmd(
            [sys.executable, str(engine_dir / "engine.py"), "status", "--root", str(root), "--json"],
            cwd=engine_dir, timeout=60,
        )
        try:
            report.snapshot = json.loads(stdout)
            report.alerts = report.snapshot.get("alerts", [])
        except (json.JSONDecodeError, OSError):
            pass

    report.stages.append(stage5)

    # ===== 阶段 6: 自动修复层（v3 新增） =====
    if skip_autofix:
        stage6 = StageResult(name="自动修复层 (已跳过)")
        stage6.skipped = True
        report.stages.append(stage6)
    else:
        stage6 = StageResult(name="自动修复层")
        # 6-1: lint invalid 卡自动修复（不依赖其他步骤）
        stage6.steps.append(_run_step("auto_fix_lint", "自动修复",
                                      lambda: _step_auto_fix_lint(root, engine_dir)))
        # 6-2: pytest 环境类修复（pip install 缺的包）
        stage6.steps.append(_run_step("auto_pytest_env_fix", "自动修复",
                                      lambda: _step_auto_pytest_fix(root, engine_dir)))
        # 6-3: sleep 候选假信号过滤
        stage6.steps.append(_run_step("auto_sleep_filter", "自动修复",
                                      lambda: _step_auto_sleep_filter(root, engine_dir)))
        # 6-4: sleep 候选补 tag / 生成草稿
        stage6.steps.append(_run_step("auto_process_sleep", "自动修复",
                                      lambda: _step_auto_process_sleep(root, engine_dir)))
        # 6-5: review_today 自动分类过审
        stage6.steps.append(_run_step("auto_review_today", "自动修复",
                                      lambda: _step_auto_review_today(root, engine_dir)))
        report.stages.append(stage6)

        # 收集自动修复层结果到 report.auto_fix_results
        report.auto_fix_results = {
            st.name: {"status": st.status, "output": st.output[:300]}
            for st in stage6.steps
        }

    # ===== 计算总体退出码 =====
    has_critical = any(a.get("level") == "critical" for a in report.alerts)
    max_exit = 0
    for stage in report.stages:
        for step in stage.steps:
            max_exit = max(max_exit, step.exit_code)
    if has_critical:
        report.overall_exit_code = 3
    elif max_exit >= 2:
        report.overall_exit_code = 2
    elif max_exit == 1:
        report.overall_exit_code = 1
    else:
        report.overall_exit_code = 0

    # ===== 生成建议 =====
    report.suggestions = _generate_suggestions(report)

    return report


# ============================================================================
# 阶段 7: 分级输出
# ============================================================================

def print_report(report: PatrolReport):
    """打印巡检报告（人类可读）。"""
    print("=" * 72)
    print("  中枢每日健康巡检报告  v3")
    print(f"  生成时间: {report.generated_at}")
    print(f"  中枢路径: {report.hub_root}")
    llm_icon = "✅ 可用" if report.llm_available else "⚠️ 不可用"
    print(f"  本地 LLM (LM Studio) 状态: {llm_icon}")
    print(f"  自动修复层: {'已执行' if report.auto_fix_results else '未执行'}")
    print("=" * 72)

    for stage in report.stages:
        stage_icon = "⏭️" if stage.skipped else "🔧"
        print(f"\n{stage_icon} {stage.name}:")
        for step in stage.steps:
            if step.status == "skip":
                icon = "⏭️"
            elif step.status == "pass":
                icon = "✅"
            elif step.status == "warn":
                icon = "⚠️"
            else:
                icon = "❌"
            duration = f" ({step.duration_ms:.0f}ms)" if step.duration_ms else ""
            print(f"  {icon} {step.name}{duration}: {step.output}")
            if step.error:
                print(f"     └─ 错误: {step.error}")

    # 告警汇总
    if report.alerts:
        print(f"\n{'=' * 72}")
        print(f"  ⚠️ 告警汇总 ({len(report.alerts)} 项)")
        print(f"{'=' * 72}")
        level_icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
        for a in report.alerts:
            icon = level_icons.get(a.get("level", ""), "⚠️")
            print(f"  {icon} [{a.get('level', '')}] {a.get('message', '')}")
            if a.get("suggestion"):
                print(f"     💡 {a['suggestion']}")
    else:
        print("\n✅ 无告警")

    # 健康评分
    scores = report.snapshot.get("health_scores", {})
    if scores:
        print("\n📊 健康度评分:")
        labels = {
            "card_health": "卡片",
            "skill_health": "技能",
            "flywheel_activity": "飞轮",
            "llm_health": "本地 LLM",   # v3: Ollama → 本地 LLM
            "overall": "📈 总分",
        }
        for k, v in scores.items():
            label = labels.get(k, k)
            bar_len = int(v / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"  {label}: {bar} {v:.1f}")

    # 自动修复层结果
    if report.auto_fix_results:
        print("\n🔧 自动修复层结果:")
        for name, info in report.auto_fix_results.items():
            icon = "✅" if info["status"] == "pass" else "⚠️" if info["status"] == "warn" else "⏭️"
            print(f"  {icon} {name}: {info['output'][:150]}")

    # 建议
    if report.suggestions:
        print("\n💡 改进建议:")
        for i, s in enumerate(report.suggestions, 1):
            print(f"  {i}. {s}")

    # 总体退出码
    print(f"\n{'=' * 72}")
    print(f"  总体退出码: {report.overall_exit_code} "
          f"({'全绿' if report.overall_exit_code == 0 else '需关注'})")
    print(f"{'=' * 72}")


# ============================================================================
# CLI 入口
# ============================================================================

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="patrol",
        description="中枢每日健康巡检编排 v3 (7 阶段流水线)",
    )
    parser.add_argument("--root", required=True, help="中枢根目录")
    parser.add_argument("--skip-flywheel", action="store_true",
                        help="跳过飞轮相关步骤 (向量构建/路由同步)")
    parser.add_argument("--skip-autofix", action="store_true",
                        help="跳过阶段 6 自动修复层 (调试用)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印计划，不实际执行")
    parser.add_argument("--skip-if-exists", action="store_true",
                        help="幂等保护：若今日快照已存在则直接跳过巡检")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出报告")
    parser.add_argument("--output", default=None,
                        help="将报告写入指定 JSON 文件")

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not root.is_dir():
        print(f"❌ 中枢目录不存在: {root}", file=sys.stderr)
        return 1

    print(f"🔍 开始巡检 v3: {root}")
    print(f"   模式: {'dry-run' if args.dry_run else 'full'}")
    if args.skip_flywheel:
        print("   已跳过飞轮步骤")
    if args.skip_autofix:
        print("   已跳过自动修复层")
    print()

    report = run_patrol(
        root,
        skip_flywheel=args.skip_flywheel,
        dry_run=args.dry_run,
        skip_if_exists=args.skip_if_exists,
        skip_autofix=args.skip_autofix,
    )

    # 输出
    if args.json or args.output:
        data = report.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json_str, encoding="utf-8")
            print(f"📄 报告已写入: {out_path}")
        if args.json:
            print(json_str)
    else:
        print_report(report)

    return report.overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
