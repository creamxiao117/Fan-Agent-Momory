# @version V1.0 / 2026-10-02 / pi / 8 步巡检流水线（唯一注册表）
"""patrol.pipeline —— 巡检的 **8 步**唯一注册表（架构重构 M0.5/Task 7）。

## 为什么从 25 步收到 8 步

改造前：**7 个阶段 / 25 个步骤 / ≥7 种报告产物**，且与提交门禁、夜间生产链**大面积重复**：

| 重复对象 | 巡检里 | 别处已有 |
|---|---|---|
| ruff / 预算 / 渲染 / markdownlint / 编码 | 各一步 | **提交门禁**（M0.5/Task 6 后为 3 道 scope-gated） |
| build-vectors | `_step_build_vectors` | **夜间链** `nightly_consolidate.cmd` 第 2 步 |
| ingest（草稿提升） | `_stage_flywheel` | **Hermes 07:40 草稿提升** |
| distill / sleep | 多步 | **夜间链** 第 1、3 步 |
| metrics / review / freshness / hub_health | 各一步 | 本质都是"健康快照"，却各写一种产物 |

⇒ 巡检的职责被稀释成"什么都跑一点"，产物 7 种而**没人定期看**（T1 观测：周产出率 ≤11%）。

## 收口后的职责边界（写进代码，不靠记忆）

- **巡检（本模块）** = **观测 + 对账 + 1 份快照**：不生产、不改数据（除自修复 lint）。
- **提交门禁** = 真值拦截（3 道 scope-gated，见 `common/gate_scope.py`）。
- **夜间链** = 生产（distill → build-vectors → render → sleep → local-summary）。

## 8 步

| # | 名 | 职责 | 产物 |
|---|---|---|---|
| 1 | `lint` | 卡片/配置/文件健康 + 自修复 + 复验（先修后验） | 无 |
| 2 | `render_check` | INDEX 渲染产物一致性 | 无 |
| 3 | `recall` | 检索召回回归（58 条金标准） | 无 |
| 4 | `reconcile` | 平台×能力对账（router_sync + capability/inventory `--check` + 平台健康） | 无 |
| 5 | `secret_sentry` | 凭证泄漏哨兵 | 无 |
| 6 | `encoding` | 全库编码/行尾卫生 | 无 |
| 7 | `tests` | pytest（+ 导入错误自修）与 ruff | 无 |
| 8 | `snapshot` | 健康快照（**唯一产物**）+ 30 天滚动清理 | `retro/snapshot-<date>.json` + `retro/daily-<date>.md` |

**产物收敛原则**：除第 8 步外，任何步骤都不得写文件——这样"巡检产出"永远只有 2 件，
且都能被第 8 步的快照解释。
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE_DIR = Path(__file__).resolve().parents[2]
if str(_HUB_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE_DIR))

from scripts.patrol.core import StepResult, _run_cmd  # noqa: E402
from scripts.patrol.steps import (  # noqa: E402
    _check_config_integrity,
    _check_file_integrity,
    _step_auto_fix_lint,
    _step_auto_pytest_fix,
    _step_lint,
    _step_pytest,
    _step_render_check,
    _step_router_sync,
    _step_ruff,
    _step_startup_budget,
    _step_vector_regression,
    _step_verify_after_fix,
)

_LOCAL_TZ = timezone(timedelta(hours=+8))
# 人读产物（`daily-*.md`）的保留天数。**不适用于 `snapshot-*.json`**：
# 那是 `rule_following_timeseries` 的输入（度量历史），不参与清理，见 `_prune`。
SNAPSHOT_KEEP_DAYS = 90

# 步骤注册表：**(名, 阶段, 实现)**——唯一事实源（测试从它派生，不再正则扫源码）
STEPS: tuple[tuple[str, str, str], ...] = (
    ("lint", "库健康", "_step_library_health"),
    ("render_check", "库健康", "_step_render_check_p"),
    ("recall", "检索质量", "_step_recall"),
    ("reconcile", "平台对账", "_step_reconcile"),
    ("secret_sentry", "安全", "_step_secret_sentry"),
    ("encoding", "文本卫生", "_step_encoding"),
    ("tests", "测试与静态检查", "_step_tests"),
    ("snapshot", "快照（唯一产物）", "_step_snapshot"),
)
STEP_ORDER: tuple[str, ...] = tuple(name for name, _stage, _fn in STEPS)


def _combine(results: list[StepResult], name: str, stage: str) -> StepResult:
    """把多个子结果合并成一个步骤结果（失败优先，其次 warn，再 pass）。"""
    fails = [r for r in results if r.status == "fail"]
    warns = [r for r in results if r.status == "warn"]
    worst = fails[0] if fails else (warns[0] if warns else None)
    status = "fail" if fails else ("warn" if warns else "pass")
    text = " | ".join(r.output.strip() for r in results if r.output.strip())
    return StepResult(
        name=name,
        stage=stage,
        status=status,
        exit_code=worst.exit_code if worst else 0,
        output=text[:600],
        meta={"sub": [r.name for r in results]},
    )


def _step_library_health(root: Path, engine_dir: Path) -> StepResult:
    """库健康 = lint + 配置/文件完整性 + **先修后验**（自修复只在此步发生）。"""
    results = [_step_lint(root), _check_config_integrity(root), _check_file_integrity(root)]
    lint = results[0]
    if lint.meta.get("invalid"):
        fix = _step_auto_fix_lint(root, engine_dir)
        results.append(fix)
        if fix.exit_code == 0:
            results.append(_step_verify_after_fix(engine_dir, {"auto_fix_lint": fix.exit_code}))
    return _combine(results, "lint", "库健康")


def _step_render_check_p(root: Path, engine_dir: Path) -> StepResult:
    """索引一致性 + 启动链预算（**合并**：两者都是"派生产物 vs 事实源"的一致性）。

    预算门禁虽已上提到提交门禁（l0 道），但那只覆盖"改到 L0 面"的提交；
    未提交的 L0 改动仍需每日兜一次（双保险口径不变，只是不再单列一步）。
    """
    results = [_step_render_check(root), _step_startup_budget()]
    return _combine(results, "render_check", "库健康")


def _step_recall(root: Path, engine_dir: Path) -> StepResult:
    """检索召回回归（原 `vector_regression`；保留其名以免门禁口径漂移）。"""
    r = _step_vector_regression(root, engine_dir)
    return StepResult(
        name="recall",
        stage="检索质量",
        status=r.status,
        exit_code=r.exit_code,
        output=r.output,
        meta=r.meta,
    )


def _step_reconcile(root: Path, engine_dir: Path) -> StepResult:
    """平台 × 能力对账：声明态（hub.config.yaml）vs 实测态（平台配置）。

    合并了旧巡检的 `platform_sync` / `platform_healthcheck` / `platform_unregistered`
    三步，并**新增**能力实测态与模块台账的 `--check`（M0 的两个产物）。
    """
    results = [_step_router_sync(root, engine_dir)]
    checks = (
        ("platform_healthcheck", [sys.executable, "-m", "scripts.platform_healthcheck"]),
        ("capability_scan", [sys.executable, "-m", "scripts.capability_scan", "--check"]),
        ("inventory", [sys.executable, "-m", "scripts.inventory", "--check"]),
    )
    for name, argv in checks:
        rc, out, err = _run_cmd(
            [*argv, "--root", str(root)] if name == "platform_healthcheck" else argv, cwd=engine_dir, timeout=120
        )
        if rc == 127:
            results.append(StepResult(name=name, stage="平台对账", status="skip", output="命令不可用，跳过"))
        elif rc == 0:
            results.append(StepResult(name=name, stage="平台对账", status="pass", output=f"✅ {name} 一致"))
        else:
            tail = (out or err).strip().splitlines()[-3:]
            results.append(
                StepResult(
                    name=name,
                    stage="平台对账",
                    status="warn",
                    exit_code=rc,
                    output=f"⚠️ {name}: " + " / ".join(tail),
                )
            )
    return _combine(results, "reconcile", "平台对账")


def _step_secret_sentry(root: Path, engine_dir: Path) -> StepResult:
    rc, out, err = _run_cmd(
        [sys.executable, "-m", "scripts.secret_sentry", "--root", str(root), "--quiet"],
        cwd=engine_dir,
        timeout=180,
    )
    if rc == 127:
        return StepResult(name="secret_sentry", stage="安全", status="skip", output="secret_sentry 不可用")
    tail = (out or err).strip().splitlines()[-2:]
    return StepResult(
        name="secret_sentry",
        stage="安全",
        status="pass" if rc == 0 else "warn",
        exit_code=rc,
        output=("✅ 无凭证泄漏" if rc == 0 else "⚠️ 检出凭证候选：" + " / ".join(tail)),
    )


def _step_encoding(root: Path, engine_dir: Path) -> StepResult:
    """全库编码/行尾卫生（第五道「行尾卫生」检查在此每天跑一遍，不依赖提交）。"""
    script = engine_dir / "scripts" / "check_encoding.py"
    rc, out, err = _run_cmd(
        [sys.executable, str(script), str(engine_dir.parent / "AgentMemoryHub"), str(engine_dir)],
        cwd=engine_dir,
        timeout=180,
    )
    bad = [ln for ln in out.splitlines() if ln.startswith("[FAIL]") or ln.startswith("[WARN]")]
    if rc == 0:
        return StepResult(name="encoding", stage="文本卫生", status="pass", output="✅ 编码/行尾 全绿")
    return StepResult(
        name="encoding",
        stage="文本卫生",
        status="warn",
        exit_code=rc,
        output="⚠️ 编码/行尾问题：" + " / ".join(bad[:3] or [out.strip()[-160:]]),
    )


def _step_tests(root: Path, engine_dir: Path) -> StepResult:
    """pytest（+ 导入错误自修）与 ruff——两者合并为一步。"""
    results = [_step_pytest(engine_dir)]
    if results[0].meta.get("has_import_error"):
        fix = _step_auto_pytest_fix(root, engine_dir)
        results.append(fix)
        if fix.exit_code == 0:
            results.append(_step_pytest(engine_dir))
    results.append(_step_ruff(engine_dir))
    return _combine(results, "tests", "测试与静态检查")


def _step_snapshot(root: Path, engine_dir: Path) -> StepResult:
    """**唯一产物步**：写 `retro/snapshot-<date>.json` + `retro/daily-<date>.md`，并清理 30 天前。"""
    rc, out, err = _run_cmd(
        [sys.executable, str(engine_dir / "engine.py"), "status", "--root", str(root), "--json"],
        cwd=engine_dir,
        timeout=120,
    )
    try:
        snap = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return StepResult(
            name="snapshot",
            stage="快照（唯一产物）",
            status="fail",
            exit_code=rc or 1,
            output=f"❌ 快照生成失败：{(err or out).strip()[:200]}",
        )

    retro = root / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    today = datetime.now(_LOCAL_TZ).date().isoformat()
    json_path = retro / f"snapshot-{today}.json"
    md_path = retro / f"daily-{today}.md"
    json_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_daily(snap, today), encoding="utf-8")
    pruned = _prune(retro)
    return StepResult(
        name="snapshot",
        stage="快照（唯一产物）",
        status="pass",
        output=f"✅ {json_path.name} + {md_path.name}" + (f"（清理 {pruned} 份旧快照）" if pruned else ""),
    )


def _render_daily(snap: dict, today: str) -> str:
    """人读快照（**从 JSON 派生**，不再让各脚本各写一种报告）。"""
    health = snap.get("health") or {}
    plat = (snap.get("platforms") or {}).get("platforms") or {}
    plat_txt = ", ".join(f"{k}={v.get('status', '?')}" for k, v in plat.items()) or "—"
    lines = [
        f"# 中枢每日快照 {today}",
        "",
        "> 由 `scripts/patrol_runner` 第 8 步生成（**巡检唯一产物**）。",
        "> 数据源 = `engine.py status --json`；不要手改本文件。",
        "",
        f"- 健康总分：{health.get('overall_score', '—')}（{health.get('overall_verdict', '—')}）",
        f"- 卡片：{json.dumps(health.get('card_health', {}), ensure_ascii=False)}",
        f"- 平台：{plat_txt}",
    ]
    alerts = snap.get("alerts") or {}
    if alerts:
        lines += ["", f"- 告警：{json.dumps(alerts, ensure_ascii=False)[:400]}"]
    for key in ("knowledge_gap", "cron_jobs"):
        if snap.get(key):
            lines.append(f"- {key}：{json.dumps(snap[key], ensure_ascii=False)[:300]}")
    return "\n".join(lines) + "\n"


def _prune(retro: Path) -> int:
    """清理超过 `SNAPSHOT_KEEP_DAYS` 的**人读**产物（防 `retro/` 无限膨胀）。

    ⚠️ **只清 `daily-*.md`，绝不动 `snapshot-*.json`**（2026-10-02 实测教训）：
    `snapshot-*.json` 是 `scripts/rule_following_timeseries.py` 的**输入**
    （T1「规则遵循/返工」指标的每日序列），删掉它们等于删掉度量历史。
    初版 `_prune` 把 30 天前的 snapshot 一并删了——实测立即表现为 `git status` 里
    7 份 tracked 快照变 D，已回退。判定原则：**先查它有没有消费者，再决定能不能删**。
    """
    cutoff = datetime.now(_LOCAL_TZ).date() - timedelta(days=SNAPSHOT_KEEP_DAYS)
    removed = 0
    for p in retro.glob("daily-*.md"):
        stamp = p.stem.split("-", 1)[-1]
        try:
            if datetime.fromisoformat(stamp).date() < cutoff:
                p.unlink()
                removed += 1
        except ValueError:
            continue
    return removed


# 供 runner 按表调用：名 → 函数
IMPL = {
    "_step_library_health": _step_library_health,
    "_step_render_check_p": _step_render_check_p,
    "_step_recall": _step_recall,
    "_step_reconcile": _step_reconcile,
    "_step_secret_sentry": _step_secret_sentry,
    "_step_encoding": _step_encoding,
    "_step_tests": _step_tests,
    "_step_snapshot": _step_snapshot,
}


def run_all(root: Path, engine_dir: Path, *, dry_run: bool = False) -> list[StepResult]:
    """按注册表顺序跑完 8 步（仅供 runner 调用；每步的异常由 `_run_step` 兜底）。"""
    out: list[StepResult] = []
    for name, stage, fn_name in STEPS:
        if dry_run:
            out.append(StepResult(name=name, stage=stage, status="skip", output="dry-run"))
            continue
        out.append(IMPL[fn_name](root, engine_dir))
    return out


__all__ = ["IMPL", "STEP_ORDER", "STEPS", "run_all"]


# 未使用但需保留导入的符号（ruff F401 显式声明）：`shutil` 供未来清理使用
_ = shutil
