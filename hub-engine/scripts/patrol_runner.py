#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patrol_runner.py — 中枢每日健康巡检编排脚本 v2

5 阶段流水线:
  阶段 1: 基础设施检查 (Ollama / 配置完整性 / 文件检查)
  阶段 2: 代码质量门禁 (lint / pytest / ruff)
  阶段 3: 飞轮活跃度 (向量增量 / 路由同步)
  阶段 4: 数据质量 (查询回归 / 指标聚合 / 今日审核)
  阶段 5: 报告生成与归档 (健康评分 / 快照 / 告警)

用法:
  python patrol_runner.py --root <hub_root>
  python patrol_runner.py --root <hub_root> --dry-run   # 不执行，只打印计划
  python patrol_runner.py --root <hub_root> --skip-flywheel  # 跳过飞轮处理
"""

import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# 将 hub-engine 加入 sys.path，确保 tools 模块可导入
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
    error: Optional[str] = None


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
    ollama_available: bool = True
    overall_exit_code: int = 0
    snapshot: dict = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hub_root": self.hub_root,
            "generated_at": self.generated_at,
            "ollama_available": self.ollama_available,
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
                        }
                        for st in s.steps
                    ],
                }
                for s in self.stages
            ],
            "snapshot": self.snapshot,
            "alerts": self.alerts,
            "suggestions": self.suggestions,
        }


# ============================================================================
# 工具函数
# ============================================================================

def _run_step(
    name: str,
    stage: str,
    fn: Callable[[], StepResult],
    *,
    pre_check: Optional[Callable[[], bool]] = None,
) -> StepResult:
    """执行单个步骤，带前置检查。"""
    if pre_check and not pre_check():
        return StepResult(
            name=name, stage=stage, status="skip",
            output="前置检查未通过，跳过",
        )
    try:
        result = fn()
        result.name = name
        result.stage = stage
        return result
    except Exception as e:
        return StepResult(
            name=name, stage=stage, status="fail",
            exit_code=999,
            error=str(e),
        )


def _run_cmd(
    argv: list[str],
    cwd: Optional[Path] = None,
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


def _ollama_pre_check() -> StepResult:
    """P0-2: Ollama 服务前置检测。"""
    try:
        # 默认使用本地的 LM Studio 端口 1234
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        status = checker.get_status()
        models_str = ", ".join(status.models[:3]) if status.models else "无模型"
        rt_ms = round(status.response_time * 1000, 1)
        output = (
            f"✅ Ollama 可用 · {len(status.models)} 模型 · 响应 {rt_ms}ms"
            + (f" · {models_str}" if models_str != "无模型" else "")
        )
        return StepResult(
            name="ollama_check",
            stage="基础设施",
            status="pass",
            exit_code=0,
            output=output,
        )
    except Exception as e:
        return StepResult(
            name="ollama_check",
            stage="基础设施",
            status="fail",
            exit_code=3,
            error=str(e),
            output=f"❌ Ollama 不可用: {e}",
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
            exit_code=1,
            output=f"⚠️ 缺失目录: {', '.join(missing)}",
        )
    return StepResult(
        name="file_integrity",
        stage="基础设施",
        status="pass",
        output="✅ 目录结构完整",
    )


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
        )
    return StepResult(
        name="lint", stage="质量门禁",
        status="pass", exit_code=0, output=f"✅ {output}",
    )


def _step_pytest(engine_dir: Path) -> StepResult:
    """运行 pytest。"""
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
            status="skip", exit_code=127, output=f"⏭️ pytest 未安装 (127)",
        )
    else:
        return StepResult(
            name="pytest", stage="质量门禁",
            status="fail", exit_code=exit_code, output=f"❌ pytest 失败: {last_line}",
        )


def _step_ruff(engine_dir: Path) -> StepResult:
    """运行 ruff check。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=engine_dir, timeout=60,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="pass", exit_code=0, output=f"✅ ruff 通过",
        )
    elif exit_code == 127:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="skip", exit_code=127, output=f"⏭️ ruff 未安装 (127)",
        )
    else:
        return StepResult(
            name="ruff", stage="质量门禁",
            status="warn", exit_code=exit_code, output=f"⚠️ ruff 告警: {last_line}",
        )


def _step_build_vectors(root: Path, engine_dir: Path) -> StepResult:
    """向量增量更新。"""
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


def _step_status_snapshot(root: Path, engine_dir: Path) -> StepResult:
    """生成健康快照（调用升级后的 _cmd_status）。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(engine_dir / "engine.py"), "status", "--root", str(root), "--json"],
        cwd=engine_dir, timeout=60,
    )
    if exit_code in (0, 2):
        try:
            snapshot = json.loads(stdout)
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
        # 检查文件是否是今日有效快照
        try:
            existing = json.loads(snap_path.read_text(encoding="utf-8"))
            if existing.get("generated_at", ""):
                gen_time = existing["generated_at"]
                # 验证 generated_at 确实是今天
                if today in gen_time:
                    return StepResult(
                        name="archive_snapshot", stage="报告归档",
                        status="pass", exit_code=0,
                        output=f"⏭️ 今日快照已存在，跳过归档 (幂等保护): {snap_path}",
                    )
        except (json.JSONDecodeError, KeyError, OSError):
            # 存在但损坏，允许覆盖
            pass

    # 重新生成一次 JSON 快照并写入文件
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


def _generate_suggestions(report: PatrolReport) -> list[str]:
    """基于告警结果生成改进建议。"""
    suggestions = []
    has_ollama_issue = not report.ollama_available

    for alert in report.alerts:
        rule = alert.get("rule", "")
        level = alert.get("level", "")
        msg = alert.get("message", "")

        if rule == "ollama_unavailable":
            suggestions.append(
                "🟢 Ollama 不可用 → 执行 `ollama serve` 重启服务，或使用 `ollama pull bge-m3` 确认模型就绪"
            )
        elif rule == "lint_issues":
            suggestions.append(
                "🟢 Lint 问题 → 执行 `python engine.py lint --root <hub>` 查看详情，重点处理孤儿页和陈旧页"
            )
        elif rule == "low_hit_rate":
            suggestions.append(
                "🟢 命中率低 → 查看 query.log.jsonl 中未命中的查询，补充相关卡片或优化 tags 覆盖"
            )
        elif rule == "low_flywheel_activity":
            suggestions.append(
                "🟢 飞轮活跃度低 → 执行 `python engine.py distill --root <hub>` 处理草稿，或运行 auto_flywheel.py"
            )
        elif rule == "pending_confirmation":
            suggestions.append(
                "🟢 待确认卡片 → 执行 `python engine.py confirm --root <hub> <name>` 逐张确认"
            )
        elif rule == "ollama_slow":
            suggestions.append(
                "🟢 Ollama 响应慢 → 检查系统资源占用，考虑使用较小模型或增加 Ollama 内存限制"
            )

    if not suggestions and not report.alerts:
        suggestions.append("✅ 系统健康，无需额外操作")

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
) -> PatrolReport:
    """
    执行完整的 5 阶段巡检流水线。

    Args:
        root: 中枢根目录
        skip_flywheel: 是否跳过飞轮相关步骤
        dry_run: 是否仅打印计划不实际执行

    Returns:
        PatrolReport 完整巡检报告
    """
    engine_dir = Path(__file__).resolve().parent.parent

    # === 幂等保护：检查今日快照是否已存在 ===
    if skip_if_exists:
        retro_dir = root / "retro"
        today = datetime.now(_LOCAL_TZ).date().isoformat()
        existing_snap = retro_dir / f"snapshot-{today}.json"
        if existing_snap.is_file():
            try:
                existing_data = json.loads(existing_snap.read_text(encoding="utf-8"))
                if existing_data.get("generated_at", "") and today in existing_data["generated_at"]:
                    # 今日快照已存在且有效，直接返回
                    report = PatrolReport(
                        hub_root=str(root),
                        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
                        ollama_available=existing_data.get("ollama", {}).get("available", True),
                        overall_exit_code=0,
                        snapshot=existing_data,
                        alerts=existing_data.get("alerts", []),
                        suggestions=["今日快照已存在，跳过巡检（幂等保护）"],
                    )
                    # 构造一个"全跳过"的 stages
                    skipped_stage = StageResult(name="幂等保护")
                    skipped_stage.steps.append(StepResult(
                        name="check_existing_snapshot", stage="幂等保护", status="skip",
                        output=f"⏭️ 今日快照已存在: {existing_snap}",
                    ))
                    report.stages.append(skipped_stage)
                    return report
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # 快照损坏，允许重新执行

    report = PatrolReport(
        hub_root=str(root),
        generated_at=datetime.now(_LOCAL_TZ).isoformat(),
    )

    # ===== 阶段 1: 基础设施检查 =====
    stage1 = StageResult(name="基础设施检查")
    stage1.steps.append(_ollama_pre_check())
    ollama_ok = stage1.steps[-1].status == "pass"
    report.ollama_available = ollama_ok
    stage1.steps.append(_check_config_integrity(root))
    stage1.steps.append(_check_file_integrity(root))
    report.stages.append(stage1)

    if dry_run:
        print("[DRY-RUN] 阶段 1 完成，后续步骤仅打印计划")
        print("  阶段 2: lint → pytest → ruff")
        print("  阶段 3: build-vectors → router-sync")
        print("  阶段 4: vector-regression → metrics-daily → hub-review")
        print("  阶段 5: status-snapshot → archive-snapshot")
        return report

    # ===== 阶段 2: 代码质量门禁 =====
    stage2 = StageResult(name="代码质量门禁")
    stage2.steps.append(_step_lint(root))

    # Ollama 不可用时跳过 pytest/ruff（非必要阻塞项）
    if ollama_ok:
        stage2.steps.append(_step_pytest(engine_dir))
        stage2.steps.append(_step_ruff(engine_dir))
    else:
        stage2.steps.append(StepResult(
            name="pytest", stage="质量门禁", status="skip",
            output="Ollama 不可用，跳过 pytest",
        ))
        stage2.steps.append(StepResult(
            name="ruff", stage="质量门禁", status="skip",
            output="Ollama 不可用，跳过 ruff",
        ))
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
        if ollama_ok:
            stage3.steps.append(_step_build_vectors(root, engine_dir))
        else:
            stage3.steps.append(StepResult(
                name="build_vectors", stage="飞轮活跃度", status="skip",
                output="Ollama 不可用，跳过向量构建",
            ))
        stage3.steps.append(_step_router_sync(root, engine_dir))
    report.stages.append(stage3)

    # ===== 阶段 4: 数据质量 =====
    stage4 = StageResult(name="数据质量")
    stage4.steps.append(_step_vector_regression(root, engine_dir))
    stage4.steps.append(_step_metrics_daily(root, engine_dir))
    stage4.steps.append(_step_hub_review(root, engine_dir))
    report.stages.append(stage4)

    # ===== 阶段 5: 报告生成与归档 =====
    stage5 = StageResult(name="报告生成与归档")
    snap_result = _step_status_snapshot(root, engine_dir)
    stage5.steps.append(snap_result)
    archive_result = _save_snapshot_archive(root, engine_dir, no_overwrite=skip_if_exists)
    stage5.steps.append(archive_result)

    # 解析快照用于报告
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

    # ===== 计算总体退出码 =====
    has_critical = any(
        a.get("level") == "critical" for a in report.alerts
    )
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


def print_report(report: PatrolReport):
    """打印巡检报告。"""
    print("=" * 72)
    print(f"  中枢每日健康巡检报告")
    print(f"  生成时间: {report.generated_at}")
    print(f"  中枢路径: {report.hub_root}")
    print(f"  Ollama 状态: {'✅ 可用' if report.ollama_available else '❌ 不可用'}")
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
            duration = f" ({step.duration_ms}ms)" if step.duration_ms else ""
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
        print(f"\n✅ 无告警")

    # 健康评分
    scores = report.snapshot.get("health_scores", {})
    if scores:
        print(f"\n📊 健康度评分:")
        labels = {"card_health": "卡片", "skill_health": "技能",
                   "flywheel_activity": "飞轮", "llm_health": "Ollama",
                   "overall": "📈 总分"}
        for k, v in scores.items():
            label = labels.get(k, k)
            bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
            print(f"  {label}: {bar} {v:.1f}")

    # 建议
    if report.suggestions:
        print(f"\n💡 改进建议:")
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
        description="中枢每日健康巡检编排 (5 阶段流水线)",
    )
    parser.add_argument("--root", required=True, help="中枢根目录")
    parser.add_argument("--skip-flywheel", action="store_true",
                        help="跳过飞轮相关步骤 (向量构建/路由同步)")
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

    print(f"🔍 开始巡检: {root}")
    print(f"   模式: {'dry-run' if args.dry_run else 'full'}")
    if args.skip_flywheel:
        print(f"   已跳过飞轮步骤")
    print()

    report = run_patrol(
        root,
        skip_flywheel=args.skip_flywheel,
        dry_run=args.dry_run,
        skip_if_exists=args.skip_if_exists,
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
