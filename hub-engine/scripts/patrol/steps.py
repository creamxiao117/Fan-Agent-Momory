# @version V3.1 / 2026-09-25 / pi / 巡检步骤实现（预检 / 质量 / 飞轮 / 数据 / 自修复 / 平台）
"""patrol.steps — 24 个巡检步骤的具体实现。

每个 `_step_*` 都返回 `StepResult`；编排（谁在什么阶段跑）在 `patrol_runner` 里，
静态扫描 `patrol_runner._run_step("<name>")` 即可拿到注册表（`tests/test_patrol_steps.py` 看守）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.patrol.core import (
    _LOCAL_TZ,
    PatrolReport,
    StepResult,
    _run_cmd,
)

_HUB_ENGINE_DIR = Path(__file__).resolve().parents[2]
if str(_HUB_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE_DIR))


def _llm_pre_check() -> StepResult:
    """阶段 1-1: 本地 LLM 服务前置检测（LM Studio）。"""
    try:
        from tools.llm_health import LLMHealthChecker

        # 默认本地 LM Studio 端口 1234
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        status = checker.get_status()
        models_str = ", ".join(status.models[:3]) if status.models else "无模型"
        rt_ms = round(status.response_time * 1000, 1)
        output = f"✅ 本地 LLM (LM Studio) 可用 · {len(status.models)} 模型 · 响应 {rt_ms}ms" + (
            f" · {models_str}" if models_str != "无模型" else ""
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
            status="warn",  # v3: 基础设施不可用降为 warn，不阻塞其他步骤
            exit_code=0,  # v3: 不再返回 exit_code=3 影响总体
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
        "rules",
        "methodology",
        "longterm",
        "experience",
        "notes",
        ".sync",
        ".sync/state",
        ".sync/drafts",
        "retro",
    ]
    missing = [d for d in required_dirs if not (root / d).is_dir()]
    if missing:
        return StepResult(
            name="file_integrity",
            stage="基础设施",
            status="warn",
            exit_code=0,  # v3: 不再设为阻塞
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
    unhealthy = len(report["orphans"]) + len(report["ghosts"]) + len(report["stale"]) + report["invalid"]
    output = (
        f"lint: orphans={len(report['orphans'])} ghosts={len(report['ghosts'])} "
        f"stale={len(report['stale'])} invalid={report['invalid']}"
    )
    if unhealthy > 0:
        return StepResult(
            name="lint",
            stage="质量门禁",
            status="warn",
            exit_code=2,
            output=f"⚠️ {output}",
            meta={
                "orphans": len(report["orphans"]),
                "ghosts": len(report["ghosts"]),
                "stale": len(report["stale"]),
                "invalid": report["invalid"],
            },
        )
    return StepResult(
        name="lint",
        stage="质量门禁",
        status="pass",
        exit_code=0,
        output=f"✅ {output}",
        meta={"orphans": 0, "ghosts": 0, "stale": 0, "invalid": 0},
    )


def _step_pytest(engine_dir: Path) -> StepResult:
    """运行 pytest。始终执行，不依赖 LLM。

    超时从 120s 提到 420s（2026-09-23）：套件实测约 104s，已贴在旧阀值
    120s 边缘，导致 2026-09-23 合并到 master 后的巡检直接
    `pytest 失败: 超时 (120s)` → 总体退出码 2。
    跳过比超时更不可接受（测试是回归网），故给足余量（锁余 ≈4x）。
    """
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=engine_dir,
        timeout=420,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="pytest",
            stage="质量门禁",
            status="pass",
            exit_code=0,
            output=f"✅ pytest 通过: {last_line}",
        )
    elif exit_code == 127:
        return StepResult(
            name="pytest",
            stage="质量门禁",
            status="skip",
            exit_code=127,
            output="⏭️ pytest 未安装 (127)",
        )
    else:
        return StepResult(
            name="pytest",
            stage="质量门禁",
            status="fail",
            exit_code=exit_code,
            output=f"❌ pytest 失败: {last_line}",
            meta={
                "has_import_error": "ModuleNotFoundError" in (stderr or stdout) or "ImportError" in (stderr or stdout)
            },
        )


def _step_ruff(engine_dir: Path) -> StepResult:
    """运行 ruff check。始终执行，不依赖 LLM。"""
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=engine_dir,
        timeout=60,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="ruff",
            stage="质量门禁",
            status="pass",
            exit_code=0,
            output="✅ ruff 通过",
        )
    elif exit_code == 127:
        return StepResult(
            name="ruff",
            stage="质量门禁",
            status="skip",
            exit_code=127,
            output="⏭️ ruff 未安装 (127)",
        )
    else:
        return StepResult(
            name="ruff",
            stage="质量门禁",
            status="warn",
            exit_code=exit_code,
            output=f"⚠️ ruff 告警: {last_line}",
        )


def _step_startup_budget() -> StepResult:
    """L0 + L1 预算门禁（spec S3 挂巡检；L1 部分 2026-09-23 新增）。

    为什么挂巡检而不挂 pre-commit：该门禁只有「内容变多才超帽」，日常提交基本不触发；
    挂 pre-commit 会拖慢每次提交，且容易被人用 --no-verify 绕过。

    直接调 `measure()`/`check()` + `measure_tiers()`/`check_tiers()`（只读），
    不重定向 stdout。不涉 LLM。
    """
    from scripts.startup_budget import (
        TOTAL_LIMIT,
        _repo_root,
        check,
        check_tiers,
        measure,
        measure_tiers,
    )

    root = _repo_root()
    rows = measure(root)
    texts = {r["name"]: r["chars"] for r in rows}
    total = sum(texts.values())
    l0_detail = " ".join(f"{r['name'].replace('.md', '')}={r['chars']}" for r in rows)

    # L1（按任务型补读）：无 tools 环境时降级为不检，不误报失败
    try:
        tier_rows = measure_tiers(root)
        tier_errs = check_tiers(tier_rows)
        l1_detail = " ".join(f"{r['tier']}={r['chars']}" for r in tier_rows)
    except ImportError:
        tier_rows, tier_errs, l1_detail = [], [], "未检(无法导入 task_tier)"

    errs = check(texts) + tier_errs
    meta = {"total": total, "limit": TOTAL_LIMIT, "l1": tier_rows, "errors": errs}
    if errs:
        return StepResult(
            name="startup_budget",
            stage="质量门禁",
            status="warn",
            exit_code=1,
            output=(f"⚠️ 预算超帽 L0 {total}/{TOTAL_LIMIT} [{l0_detail}] | L1 [{l1_detail}]：{'; '.join(errs)}"),
            meta=meta,
        )
    return StepResult(
        name="startup_budget",
        stage="质量门禁",
        status="pass",
        exit_code=0,
        output=f"✅ 预算 L0 {total}/{TOTAL_LIMIT}（{l0_detail}） | L1（{l1_detail}）",
        meta=meta,
    )


# ----- 阶段 3: 飞轮活跃度 -----


def _step_build_vectors(root: Path, engine_dir: Path) -> StepResult:
    """向量增量更新。依赖本地 LLM 可用性。"""
    exit_code, stdout, stderr = _run_cmd(
        [
            sys.executable,
            str(engine_dir / "engine.py"),
            "build-vectors",
            "--root",
            str(root),
        ],
        cwd=engine_dir,
        timeout=300,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="build_vectors",
            stage="飞轮活跃度",
            status="pass",
            exit_code=0,
            output=f"✅ 向量构建: {last_line}",
        )
    elif exit_code == 2:
        return StepResult(
            name="build_vectors",
            stage="飞轮活跃度",
            status="warn",
            exit_code=2,
            output=f"⚠️ 向量通道退化: {last_line}",
        )
    else:
        return StepResult(
            name="build_vectors",
            stage="飞轮活跃度",
            status="fail",
            exit_code=exit_code,
            output=f"❌ 向量构建失败: {last_line}",
        )


def _step_router_sync(root: Path, engine_dir: Path) -> StepResult:
    """路由表同步检查。"""
    sync_script = engine_dir / "scripts" / "router_sync.py"
    if not sync_script.is_file():
        return StepResult(
            name="router_sync",
            stage="飞轮活跃度",
            status="skip",
            exit_code=0,
            output="⏭️ router_sync.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(sync_script), "--root", str(root)],
        cwd=engine_dir,
        timeout=60,
    )
    if exit_code == 0:
        return StepResult(
            name="router_sync",
            stage="飞轮活跃度",
            status="pass",
            exit_code=0,
            output="✅ 路由表同步检查通过",
        )
    return StepResult(
        name="router_sync",
        stage="飞轮活跃度",
        status="warn",
        exit_code=exit_code,
        output=f"⚠️ 路由表同步异常: {(stderr or stdout).strip()[:200]}",
    )


# ----- 阶段 4: 数据质量 -----


def _step_vector_regression(root: Path, engine_dir: Path) -> StepResult:
    """固定查询集回归测试。"""
    bench_script = engine_dir / "scripts" / "vector_bench.py"
    if not bench_script.is_file():
        return StepResult(
            name="vector_regression",
            stage="数据质量",
            status="skip",
            exit_code=0,
            output="⏭️ vector_bench.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        # `--fail-below 0.8`：**此前被遗漏**，导致本步骤恒 exit 0（即使命中率 50% 也判 pass，
        # 即 2026-09-23 记录的「每日巡检门禁失效」归因）。
        #
        # ⚠️ 阈值必须先修好夹具才能加（2026-09-24 已一并修）：夹具曾指向两张已归档卡，
        # 上限卡在 4/6=67% ⇒ 若当时就加 0.8，本步骤会**永久红灯**。
        # 夹具改正后实测融合命中率 100%，阀値 0.8 留有 1 条余量。
        [sys.executable, str(bench_script), "--real", str(root), "--fail-below", "0.8"],
        cwd=engine_dir,
        timeout=120,
    )
    last_line = (stdout or stderr or "(无输出)").strip().splitlines()[-1] if (stdout or stderr) else "(无输出)"
    if exit_code == 0:
        return StepResult(
            name="vector_regression",
            stage="数据质量",
            status="pass",
            exit_code=0,
            output=f"✅ 向量回归: {last_line}",
        )
    else:
        return StepResult(
            name="vector_regression",
            stage="数据质量",
            status="warn",
            exit_code=exit_code,
            output=f"⚠️ 向量回归: {last_line}",
        )


def _step_metrics_daily(root: Path, engine_dir: Path) -> StepResult:
    """每日指标聚合。"""
    metrics_script = engine_dir / "scripts" / "metrics_daily.py"
    if not metrics_script.is_file():
        return StepResult(
            name="metrics_daily",
            stage="数据质量",
            status="skip",
            exit_code=0,
            output="⏭️ metrics_daily.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(metrics_script), "--root", str(root)],
        cwd=engine_dir,
        timeout=30,
    )
    if exit_code == 0:
        return StepResult(
            name="metrics_daily",
            stage="数据质量",
            status="pass",
            exit_code=0,
            output=f"✅ 指标聚合: {(stdout or '').strip()[:200]}",
        )
    return StepResult(
        name="metrics_daily",
        stage="数据质量",
        status="warn",
        exit_code=exit_code,
        output=f"⚠️ 指标聚合: {(stderr or stdout).strip()[:200]}",
    )


def _step_hub_review(root: Path, engine_dir: Path) -> StepResult:
    """今日审核清单。"""
    review_script = engine_dir / "scripts" / "hub_review_today.py"
    if not review_script.is_file():
        return StepResult(
            name="hub_review",
            stage="数据质量",
            status="skip",
            exit_code=0,
            output="⏭️ hub_review_today.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(review_script), "--root", str(root)],
        cwd=engine_dir,
        timeout=30,
    )
    if exit_code == 0:
        return StepResult(
            name="hub_review",
            stage="数据质量",
            status="pass",
            exit_code=0,
            output=f"✅ 今日审核: {(stdout or '').strip()[:300]}",
        )
    return StepResult(
        name="hub_review",
        stage="数据质量",
        status="warn",
        exit_code=exit_code,
        output=f"⚠️ 今日审核: {(stderr or stdout).strip()[:300]}",
    )


# ----- 阶段 5: 报告生成与归档 -----


def _step_status_snapshot(root: Path, engine_dir: Path) -> StepResult:
    """生成健康快照（调用升级后的 _cmd_status）。"""
    exit_code, stdout, stderr = _run_cmd(
        [
            sys.executable,
            str(engine_dir / "engine.py"),
            "status",
            "--root",
            str(root),
            "--json",
        ],
        cwd=engine_dir,
        timeout=60,
    )
    if exit_code in (0, 2):
        try:
            json.loads(stdout)
            return StepResult(
                name="status_snapshot",
                stage="报告归档",
                status="pass",
                exit_code=exit_code,
                output=f"✅ 快照生成 (exit={exit_code})",
            )
        except json.JSONDecodeError:
            pass
    return StepResult(
        name="status_snapshot",
        stage="报告归档",
        status="fail",
        exit_code=exit_code,
        output=f"❌ 快照生成失败: {(stderr or stdout).strip()[:200]}",
    )


def _save_snapshot_archive(root: Path, engine_dir: Path, *, no_overwrite: bool = False) -> StepResult:
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
                    name="archive_snapshot",
                    stage="报告归档",
                    status="pass",
                    exit_code=0,
                    output=f"⏭️ 今日快照已存在，跳过归档 (幂等保护): {snap_path}",
                )
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # 存在但损坏，允许覆盖

    # 生成一次 JSON 快照并写入
    exit_code, stdout, stderr = _run_cmd(
        [
            sys.executable,
            str(engine_dir / "engine.py"),
            "status",
            "--root",
            str(root),
            "--json",
        ],
        cwd=engine_dir,
        timeout=60,
    )
    if exit_code in (0, 2):
        try:
            data = json.loads(stdout)
            snap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return StepResult(
                name="archive_snapshot",
                stage="报告归档",
                status="pass",
                exit_code=0,
                output=f"✅ 快照已归档: {snap_path}",
            )
        except (json.JSONDecodeError, OSError) as e:
            return StepResult(
                name="archive_snapshot",
                stage="报告归档",
                status="fail",
                exit_code=1,
                error=str(e),
                output=f"❌ 归档失败: {e}",
            )
    return StepResult(
        name="archive_snapshot",
        stage="报告归档",
        status="fail",
        exit_code=exit_code,
        output=f"❌ 快照生成失败: {(stderr or stdout).strip()[:200]}",
    )


# ============================================================================
# 阶段 6: 自动修复层（v3 新增）
# ============================================================================


def _step_freshness_check(root: Path, engine_dir: Path) -> StepResult:
    """任务8：知识新鲜度检测。

    调用 stale_detect.py 标记 reuse_count=0 且 N 天未更新的卡/技能。
    严重陈旧时产生 alert；不自动删除（只标记）。
    """
    import subprocess

    # SkillHub 检出根：env → hub.config.yaml:external_paths.skillhub → 内置默认（单点在 common.config）
    # 未配置时不猜路径，直接跳过并把原因写进巡检报告（原为写死个人盘符路径）
    from common.config import external_path

    skillhub = external_path("skillhub", root)
    skillhub_root_str = os.environ.get("SKILLHUB_ROOT") or (str(skillhub) if skillhub else "")
    script = engine_dir / "scripts" / "stale_detect.py"
    if not skillhub_root_str:
        return StepResult(
            name="freshness_check",
            stage="新鲜度",
            status="skip",
            output="SkillHub 根未配置（设 SKILLHUB_ROOT 或 hub.config.yaml:external_paths.skillhub）",
        )
    # 注意：StepResult 的 name/stage/status 均为必填，漏传 stage 会抛 TypeError，
    # 被 _run_step 兜底成 exit_code=999 的假故障（2026-09-15 修复）。
    if not script.exists():
        return StepResult(
            name="freshness_check",
            stage="新鲜度",
            status="skip",
            output="stale_detect.py 缺失",
            exit_code=0,
        )
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(script),
                "--hub-root",
                str(root),
                "--skillhub-root",
                skillhub_root_str,
                "--days",
                "60",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return StepResult(
            name="freshness_check",
            stage="新鲜度",
            status="pass" if r.returncode == 0 else "fail",
            output=r.stdout[-300:] + r.stderr[-200:],
            exit_code=r.returncode,
        )
    except subprocess.TimeoutExpired:
        return StepResult(
            name="freshness_check",
            stage="新鲜度",
            status="fail",
            output="timeout",
            exit_code=1,
        )


def _step_verify_after_fix(engine_dir: Path, fix_results: dict) -> StepResult:
    """任务4：自动修复后验证（pytest + ruff）。

    跑最小验证：pytest 增量 + ruff check。
    任一失败则产生 critical 告警，避免静默通过。
    """

    cmds = [
        (
            "pytest_smoke",
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-x"],
        ),
        ("ruff_check", [sys.executable, "-m", "ruff", "check", "."]),
    ]
    failed: list[str] = []
    outputs: list[str] = []
    for name, cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(engine_dir))
            outputs.append(f"[{name}] exit={r.returncode}")
            if r.returncode != 0:
                failed.append(f"{name}(exit={r.returncode})")
                outputs.append(r.stdout[-200:] + r.stderr[-200:])
        except subprocess.TimeoutExpired:
            failed.append(f"{name}(timeout)")
        except FileNotFoundError as exc:
            outputs.append(f"[{name}] missing: {exc}")

    if failed:
        return StepResult(
            name="verify_after_fix",
            stage="验证",
            status="fail",
            output="\n".join(outputs),
            exit_code=1,
        )
    return StepResult(
        name="verify_after_fix",
        stage="验证",
        status="pass",
        output="\n".join(outputs),
        exit_code=0,
    )


def _step_auto_fix_lint(root: Path, engine_dir: Path) -> StepResult:
    """auto_fix_lint: lint invalid 卡自动补 frontmatter。"""
    fix_script = engine_dir / "scripts" / "auto_fix_lint.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_fix_lint",
            stage="自动修复",
            status="skip",
            output="⏭️ auto_fix_lint.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir,
        timeout=60,
    )
    text = (stdout or stderr or "").strip()
    fixed = "修复" in text and "0" not in text.split("修复")[1].split("张")[0] if "修复" in text else False
    return StepResult(
        name="auto_fix_lint",
        stage="自动修复",
        status="pass" if fixed or exit_code == 0 else "warn",
        exit_code=0,
        output=f"✅ {text[:200]}" if exit_code == 0 else f"⚠️ {text[:200]}",
    )


def _step_auto_pytest_fix(root: Path, engine_dir: Path) -> StepResult:
    """auto_pytest_env_fix: pytest 环境类失败自动修复。"""
    fix_script = engine_dir / "scripts" / "auto_pytest_env_fix.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_pytest_env_fix",
            stage="自动修复",
            status="skip",
            output="⏭️ auto_pytest_env_fix.py 不存在，跳过",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir,
        # 外层超时必须 **大于** 脚本内部的 pytest 超时（auto_pytest_env_fix.py 用 180s），
        # 否则外层永远先超时（2026-09-23 实测：外层 120s vs 内层 180s）。
        timeout=420,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_pytest_env_fix",
        stage="自动修复",
        status="pass" if exit_code == 0 else "warn",
        exit_code=0,
        output=f"✅ {text[:200]}" if exit_code == 0 else f"⚠️ {text[:200]}",
    )


def _step_auto_sleep_filter(root: Path, engine_dir: Path) -> StepResult:
    """auto_sleep_filter: sleep 候选假信号自动过滤。"""
    fix_script = engine_dir / "scripts" / "auto_sleep_filter.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_sleep_filter",
            stage="自动修复",
            status="skip",
            output="⏭️ auto_sleep_filter.py 不存在，跳过",
        )
    _exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root), "--since-days", "3"],
        cwd=engine_dir,
        timeout=60,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_sleep_filter",
        stage="自动修复",
        status="pass",
        exit_code=0,
        output=f"✅ {text[:200]}",
    )


def _step_auto_process_sleep(root: Path, engine_dir: Path) -> StepResult:
    """auto_process_sleep: sleep 候选自动补 tag / 生成草稿。"""
    fix_script = engine_dir / "scripts" / "auto_process_sleep.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_process_sleep",
            stage="自动修复",
            status="skip",
            output="⏭️ auto_process_sleep.py 不存在，跳过",
        )
    _exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root), "--since-days", "3"],
        cwd=engine_dir,
        timeout=60,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_process_sleep",
        stage="自动修复",
        status="pass",
        exit_code=0,
        output=f"✅ {text[:200]}",
    )


def _step_auto_review_today(root: Path, engine_dir: Path) -> StepResult:
    """auto_review_today: review_today 按 type 分类自动过/留。"""
    fix_script = engine_dir / "scripts" / "auto_review_today.py"
    if not fix_script.is_file():
        return StepResult(
            name="auto_review_today",
            stage="自动修复",
            status="skip",
            output="⏭️ auto_review_today.py 不存在，跳过",
        )
    _exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(fix_script), "--root", str(root)],
        cwd=engine_dir,
        timeout=30,
    )
    text = (stdout or stderr or "").strip()
    return StepResult(
        name="auto_review_today",
        stage="自动修复",
        status="pass",
        exit_code=0,
        output=f"✅ {text[:200]}",
    )


def _generate_suggestions(report: PatrolReport) -> list[str]:
    """基于告警结果生成改进建议。"""
    suggestions = []

    for alert in report.alerts:
        rule = alert.get("rule", "")
        alert.get("message", "")

        if rule == "local_llm_unavailable":
            suggestions.append(
                "🟢 本地 LLM 不可用 → 检查 LM Studio 是否在运行，确认 API 端口 1234 可达；"
                "（OmniRoute 已于 2026-09-15 从兜底移除；本地端点不可用时应人工介入）"
            )
        elif rule == "local_llm_slow":
            suggestions.append("🟢 本地 LLM 响应慢 → 检查 LM Studio 资源占用，考虑使用较小模型或开启 GPU 加速")
        elif rule == "lint_issues":
            suggestions.append(
                "🟢 Lint 问题 → 已由 auto_fix_lint 自动修复 invalid 卡 frontmatter；孤儿页和陈旧页需人工审核后手动处理"
            )
        elif rule == "low_hit_rate":
            suggestions.append(
                "🟢 命中率低 → 已由 auto_sleep_filter + auto_process_sleep 自动处理 sleep 候选；"
                "查看 .sync/drafts/auto_sleep_draft/ 中的草稿卡补充完整"
            )
        elif rule == "low_flywheel_activity":
            suggestions.append("🟢 飞轮活跃度低 → 补充新经验卡或执行 `python engine.py distill` 处理草稿")
        elif rule == "pending_confirmation":
            suggestions.append(
                "🟢 待确认卡片 → 已由 auto_review_today 自动跳过非 rule/methodology 类卡；"
                "review_today.md 中仅剩 rule/methodology 类卡需人工确认"
            )

    if not suggestions and not report.alerts:
        suggestions.append("✅ 系统健康，自动修复层已处理完毕，无需额外操作")

    return suggestions


def _step_platform_sync_check(root: Path, engine_dir: Path) -> StepResult:
    """平台 MCP 块一致性（platform_sync.py dry-run）。漂移 → exit 1（告警级，不阻断）。"""
    script = engine_dir / "scripts" / "platform_sync.py"
    if not script.exists():
        return StepResult(
            name="platform_sync",
            stage="平台一致性",
            status="skip",
            output="platform_sync.py 缺失",
        )
    exit_code, stdout, stderr = _run_cmd(
        [sys.executable, str(script), "--root", str(root)], cwd=engine_dir, timeout=120
    )
    lines = [s.strip() for s in ((stdout or "") + (stderr or "")).splitlines() if s.strip()]
    drift = [s for s in lines if ("需同步" in s or "❌" in s)]
    if exit_code == 0:
        return StepResult(
            name="platform_sync",
            stage="平台一致性",
            status="pass",
            exit_code=0,
            output="✅ MCP 块与 platforms.yaml 一致",
        )
    return StepResult(
        name="platform_sync",
        stage="平台一致性",
        status="fail",
        exit_code=1,
        output="⚠️ 检出漂移: " + " | ".join(drift or lines[-2:])[:300],
    )


def _step_platform_healthcheck(root: Path, engine_dir: Path) -> StepResult:
    """5+ 平台统一健康检查（platform_healthcheck.py）。非绿 → exit 1。"""
    script = engine_dir / "scripts" / "platform_healthcheck.py"
    if not script.exists():
        return StepResult(
            name="platform_healthcheck",
            stage="平台一致性",
            status="skip",
            output="platform_healthcheck.py 缺失",
        )
    exit_code, stdout, stderr = _run_cmd([sys.executable, str(script)], cwd=engine_dir, timeout=180)
    lines = [s.strip() for s in ((stdout or "") + (stderr or "")).splitlines() if s.strip()]
    bad = [s for s in lines if ("YELLOW" in s or "RED" in s)]
    if exit_code == 0:
        return StepResult(
            name="platform_healthcheck",
            stage="平台一致性",
            status="pass",
            exit_code=0,
            output="✅ 平台健康检查全 GREEN",
        )
    return StepResult(
        name="platform_healthcheck",
        stage="平台一致性",
        status="fail",
        exit_code=1,
        output="⚠️ 非绿平台: " + " | ".join(bad)[:300],
    )


def _step_platform_unregistered(root: Path, engine_dir: Path) -> StepResult:
    """未接入平台提示（platform_unregistered.py）。纯信息级，恒为 pass。"""
    script = engine_dir / "scripts" / "platform_unregistered.py"
    if not script.exists():
        return StepResult(
            name="platform_unregistered",
            stage="平台一致性",
            status="skip",
            output="platform_unregistered.py 缺失",
        )
    _exit_code, stdout, _stderr = _run_cmd(
        [sys.executable, str(script), "--root", str(root)], cwd=engine_dir, timeout=120
    )
    cand = [s.strip() for s in (stdout or "").splitlines() if s.strip().startswith("•")]
    if not cand:
        return StepResult(
            name="platform_unregistered",
            stage="平台一致性",
            status="pass",
            exit_code=0,
            output="✅ 无未接入平台候选",
        )
    return StepResult(
        name="platform_unregistered",
        stage="平台一致性",
        status="pass",
        exit_code=0,
        output=f"ℹ️ {len(cand)} 个候选待接入: " + " | ".join(cand)[:300],
    )
