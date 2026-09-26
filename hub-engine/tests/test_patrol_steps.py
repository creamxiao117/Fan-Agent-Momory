# @version V1.0 / 2026-09-24 / 巡检步骤测试补齐（WORK.md P1「补 16 个巡检步骤测试」）
"""巡检步骤（patrol_runner 的 24 个注册步骤）逐步测试。

## 为什么需要

此前 20 步巡检里只有极少数步骤有测试，且都是**间接**覆盖（测的是被调用的脚本，
如 `test_metrics_daily.py` 测 `scripts/metrics_daily.py`）。**步骤函数本身**——
即「子进程退出码 → StepResult 状态」的判定层——几乎无测试，
而它正是巡检门禁的**可信度来源**：判错就会出现「红灯假警报」或「红灯被吞成绿灯」。

本文件覆盖每个步骤函数的**判定契约**，用替身替换外部子进程（`_run_cmd` / `subprocess.run`），
不真跑 pytest/ruff/LM Studio，因此快且稳定。

## 两类断言

1. **契约**：24 个步骤逐个跑一遍（外部命令用替身），断言
   `name` 与注册名一致、`status` 合法、`exit_code` 非负 —— 防「漏传 stage/字段」这类
   曾把步骤炸成 exit_code=999 假故障的缺陷（见 test_snapshot_baseline_and_freshness.py 缺陷 B）。
2. **判定**：每个步骤的正常/告警/失败分支各断言一次，重点钉死三个历史缺陷：
   - `vector_regression` 必须带 `--fail-below 0.8`（曾遗漏 ⇒ 命中率 50% 也判 PASS）
   - `pytest` / `auto_pytest_env_fix` 的外层超时必须 > 内层（曾外 120s < 内 180s ⇒ 内层永不生效）
   - `freshness_check` 的 StepResult 必须带 stage（漏传 ⇒ TypeError ⇒ 假故障）
"""

from __future__ import annotations

import json
import re
import subprocess
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.patrol.steps as patrol_steps
import scripts.patrol_runner as patrol

_VALID_STATUS = {"pass", "warn", "fail", "skip"}
_CN_TZ = timezone(timedelta(hours=+8))


# ---------------------------------------------------------------------------
# 夹具与替身
# ---------------------------------------------------------------------------


@pytest.fixture()
def patrol_tree(tmp_path: Path):
    """最小中枢树：hub = <tmp>/AgentMemoryHub，engine = <tmp>/hub-engine。

    目录结构按 `_check_file_integrity` / `_check_config_integrity` 的要求布置，
    使「完整树 ⇒ pass」与「缺项 ⇒ 告警」两条分支都能测。
    """
    hub = tmp_path / "AgentMemoryHub"
    engine = tmp_path / "hub-engine"
    for d in (
        "rules",
        "methodology",
        "longterm",
        "experience",
        "notes",
        ".sync",
        ".sync/state",
        ".sync/drafts",
        "retro",
    ):
        (hub / d).mkdir(parents=True, exist_ok=True)
    (hub / "hub.config.yaml").write_text("name: test-hub\n", encoding="utf-8")
    (hub / "INDEX.md").write_text("# 索引\n", encoding="utf-8")
    (engine / "config").mkdir(parents=True, exist_ok=True)
    (engine / "config" / "engine.config.yaml").write_text("x: 1\n", encoding="utf-8")
    (engine / "scripts").mkdir(parents=True, exist_ok=True)
    return hub, engine


def _touch(engine: Path, *names: str) -> None:
    """造出步骤前置检查要求的脚本文件（内容无关，只测存在性分支）。"""
    for n in names:
        (engine / "scripts" / n).write_text("", encoding="utf-8")


def _boom(*_args, **_kwargs):
    """替身：模拟本地 LLM 不可达。"""
    raise RuntimeError("skip-live")


class FakeCmd:
    """`_run_cmd` 的替身：记录调用参数 + 返回预设 (rc, stdout, stderr)。"""

    def __init__(self, rc: int = 0, out: str = "", err: str = ""):
        self.rc, self.out, self.err = rc, out, err
        self.calls: list[dict] = []

    def __call__(self, argv, cwd=None, timeout=300):
        self.calls.append({"argv": [str(a) for a in argv], "cwd": cwd, "timeout": timeout})
        return self.rc, self.out, self.err

    @property
    def last(self) -> dict:
        return self.calls[-1]


class FakeRun:
    """`subprocess.run` 的替身（freshness_check / verify_after_fix 直接调它）。"""

    def __init__(self, rc: int = 0, out: str = "", err: str = "", raise_timeout: bool = False):
        self.rc, self.out, self.err = rc, out, err
        self.raise_timeout = raise_timeout
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": [str(a) for a in argv], "kwargs": kwargs})
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd=str(argv), timeout=kwargs.get("timeout", 0))
        return types.SimpleNamespace(returncode=self.rc, stdout=self.out, stderr=self.err)


# ---------------------------------------------------------------------------
# 契约：24 个注册步骤逐个跑通
# ---------------------------------------------------------------------------

_STEP_CALLS = [
    ("llm_check", lambda hub, eng: patrol._llm_pre_check()),
    ("config_integrity", lambda hub, eng: patrol._check_config_integrity(hub)),
    ("file_integrity", lambda hub, eng: patrol._check_file_integrity(hub)),
    ("lint", lambda hub, eng: patrol._step_lint(hub)),
    ("pytest", lambda hub, eng: patrol._step_pytest(eng)),
    ("ruff", lambda hub, eng: patrol._step_ruff(eng)),
    ("startup_budget", lambda hub, eng: patrol._step_startup_budget()),
    ("build_vectors", lambda hub, eng: patrol._step_build_vectors(hub, eng)),
    ("router_sync", lambda hub, eng: patrol._step_router_sync(hub, eng)),
    ("vector_regression", lambda hub, eng: patrol._step_vector_regression(hub, eng)),
    ("metrics_daily", lambda hub, eng: patrol._step_metrics_daily(hub, eng)),
    ("hub_review", lambda hub, eng: patrol._step_hub_review(hub, eng)),
    ("status_snapshot", lambda hub, eng: patrol._step_status_snapshot(hub, eng)),
    ("archive_snapshot", lambda hub, eng: patrol._save_snapshot_archive(hub, eng)),
    ("auto_fix_lint", lambda hub, eng: patrol._step_auto_fix_lint(hub, eng)),
    ("auto_pytest_env_fix", lambda hub, eng: patrol._step_auto_pytest_fix(hub, eng)),
    ("auto_sleep_filter", lambda hub, eng: patrol._step_auto_sleep_filter(hub, eng)),
    ("auto_process_sleep", lambda hub, eng: patrol._step_auto_process_sleep(hub, eng)),
    ("auto_review_today", lambda hub, eng: patrol._step_auto_review_today(hub, eng)),
    ("verify_after_fix", lambda hub, eng: patrol._step_verify_after_fix(eng, {})),
    ("freshness_check", lambda hub, eng: patrol._step_freshness_check(hub, eng)),
    ("platform_sync", lambda hub, eng: patrol._step_platform_sync_check(hub, eng)),
    (
        "platform_healthcheck",
        lambda hub, eng: patrol._step_platform_healthcheck(hub, eng),
    ),
    (
        "platform_unregistered",
        lambda hub, eng: patrol._step_platform_unregistered(hub, eng),
    ),
]


def _registered_step_names() -> list[str]:
    """从源码静态提取 `_run_step("name", ...)` 的注册名（顺序即执行顺序）。"""
    src = (Path(patrol.__file__)).read_text(encoding="utf-8")
    return re.findall(r'_run_step\(\s*"([a-z_0-9]+)"', src)


def test_step_table_covers_every_registered_step():
    """任何新增的巡检步骤都必须有测试条目（漏了这里会红）。"""
    registered = set(_registered_step_names())
    covered = {name for name, _ in _STEP_CALLS}
    assert registered - covered == set(), f"新增步骤未覆盖: {sorted(registered - covered)}"
    assert len(registered) >= 24, f"注册步骤数异常: {len(registered)}"


@pytest.mark.parametrize(("name", "call"), _STEP_CALLS, ids=[n for n, _ in _STEP_CALLS])
def test_step_contract(patrol_tree, monkeypatch, name, call):
    """每个步骤都要返回 StepResult：名字正确、状态合法、退出码非负。"""
    hub, engine = patrol_tree
    _touch(
        engine,
        "router_sync.py",
        "vector_bench.py",
        "metrics_daily.py",
        "hub_review_today.py",
        "auto_fix_lint.py",
        "auto_pytest_env_fix.py",
        "auto_sleep_filter.py",
        "auto_process_sleep.py",
        "auto_review_today.py",
        "stale_detect.py",
        "platform_sync.py",
        "platform_healthcheck.py",
        "platform_unregistered.py",
    )
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, '{"cards": 1}'))
    monkeypatch.setattr(subprocess, "run", FakeRun(0, "ok"))
    monkeypatch.setattr(
        "tools.lint.lint",
        lambda root: {"orphans": [], "ghosts": [], "stale": [], "invalid": 0},
    )
    # 不碰真实 LM Studio
    monkeypatch.setattr("tools.llm_health.LLMHealthChecker.get_instance", classmethod(_boom))

    result = patrol._run_step(name, "(契约)", lambda: call(hub, engine))

    assert result.name == name
    assert result.status in _VALID_STATUS, f"{name} 状态非法: {result.status}"
    assert result.exit_code >= 0, f"{name} 退出码为负: {result.exit_code}"
    assert result.error is None or result.status != "pass", f"{name} 带 error 却判 pass: {result.error}"


# ---------------------------------------------------------------------------
# 包装层：_run_step
# ---------------------------------------------------------------------------


def test_run_step_skip_when_precheck_fails():
    r = patrol._run_step("x", "s", lambda: pytest.fail("不应执行"), pre_check=lambda: False)
    assert r.status == "skip" and r.exit_code == 0


def test_run_step_exception_becomes_fail_999():
    """步骤内部抛错必须被兜底成 fail+999（而不是让整轮巡检崩掉）。"""

    def boom():
        raise TypeError("StepResult 漏传 stage")

    r = patrol._run_step("x", "s", boom)
    assert r.status == "fail" and r.exit_code == 999 and "stage" in (r.error or "")


def test_run_step_keeps_registered_name_over_function_default():
    """步骤函数里写死的 name 不允许覆盖注册名（否则报告里会出现两个名字）。"""
    r = patrol._run_step("registered", "s", lambda: patrol.StepResult(name="inner", status="pass"))
    assert r.name == "registered"


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------


def test_llm_check_degrades_to_warn_without_blocking(monkeypatch):
    """LM Studio 不可用 ⇒ warn 且 exit_code=0（v3 起不阻塞整体巡检）。"""
    monkeypatch.setattr("tools.llm_health.LLMHealthChecker.get_instance", classmethod(_boom))
    r = patrol._llm_pre_check()
    assert r.status == "warn" and r.exit_code == 0 and "不可用" in r.output


def test_config_integrity_pass_on_complete_tree(patrol_tree):
    hub, _ = patrol_tree
    r = patrol._check_config_integrity(hub)
    assert r.status == "pass" and r.exit_code == 0


def test_config_integrity_fails_blocking_on_missing_index(patrol_tree):
    """缺 INDEX.md 是阻塞级（exit_code=3）。"""
    hub, _ = patrol_tree
    (hub / "INDEX.md").unlink()
    r = patrol._check_config_integrity(hub)
    assert r.status == "fail" and r.exit_code == 3 and "INDEX.md 缺失" in r.output


def test_file_integrity_warns_but_does_not_block(patrol_tree):
    hub, _ = patrol_tree
    import shutil

    shutil.rmtree(hub / "notes")
    r = patrol._check_file_integrity(hub)
    assert r.status == "warn" and r.exit_code == 0 and "notes" in r.output


def test_file_integrity_pass_on_complete_tree(patrol_tree):
    hub, _ = patrol_tree
    assert patrol._check_file_integrity(hub).status == "pass"


# ---------------------------------------------------------------------------
# 质量门禁
# ---------------------------------------------------------------------------


def test_lint_unhealthy_counts_to_warn_exit2(patrol_tree, monkeypatch):
    hub, _ = patrol_tree
    monkeypatch.setattr(
        "tools.lint.lint",
        lambda root: {"orphans": ["a"], "ghosts": [], "stale": [], "invalid": 2},
    )
    r = patrol._step_lint(hub)
    assert r.status == "warn" and r.exit_code == 2
    assert r.meta["orphans"] == 1 and r.meta["invalid"] == 2


def test_lint_clean_is_pass(patrol_tree, monkeypatch):
    hub, _ = patrol_tree
    monkeypatch.setattr(
        "tools.lint.lint",
        lambda root: {"orphans": [], "ghosts": [], "stale": [], "invalid": 0},
    )
    r = patrol._step_lint(hub)
    assert r.status == "pass" and r.meta["invalid"] == 0


@pytest.mark.parametrize(
    ("rc", "status"),
    [(0, "pass"), (127, "skip"), (1, "fail"), (2, "fail")],
)
def test_pytest_exit_code_mapping(patrol_tree, monkeypatch, rc, status):
    _, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(rc, "1 passed"))
    r = patrol._step_pytest(engine)
    assert r.status == status and r.exit_code == rc


def test_pytest_flags_import_error_for_autofix(patrol_tree, monkeypatch):
    """meta.has_import_error 决定 auto_pytest_env_fix 是否值得跑。"""
    _, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "", "ModuleNotFoundError: No module named 'x'"))
    assert patrol._step_pytest(engine).meta["has_import_error"] is True


def test_pytest_timeout_exceeds_inner_suite_budget(patrol_tree, monkeypatch):
    """外层超时必须 > 套件实测时长（曾 120s 卡边 ⇒ 合并后首跑即假失败）。"""
    _, engine = patrol_tree
    fake = FakeCmd(0, "ok")
    monkeypatch.setattr(patrol_steps, "_run_cmd", fake)
    patrol._step_pytest(engine)
    assert fake.last["timeout"] >= 420


@pytest.mark.parametrize(
    ("rc", "status"),
    [(0, "pass"), (127, "skip"), (1, "warn"), (2, "warn")],
)
def test_ruff_never_blocks(patrol_tree, monkeypatch, rc, status):
    """ruff 非零只告警（exit_code 原样保留，但状态不是 fail）。"""
    _, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(rc, "found 3 errors"))
    r = patrol._step_ruff(engine)
    assert r.status == status and r.exit_code == rc


def test_startup_budget_runs_against_real_repo():
    """预算门禁是只读测量：真实仓库上必须能给出 pass/warn，且带总数元信息。"""
    r = patrol._step_startup_budget()
    assert r.status in {"pass", "warn"}
    assert r.meta["total"] > 0 and r.meta["limit"] > 0


# ---------------------------------------------------------------------------
# 飞轮活跃度
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rc", "status", "exit_code"),
    [(0, "pass", 0), (2, "warn", 2), (5, "fail", 5)],
)
def test_build_vectors_exit_code_mapping(patrol_tree, monkeypatch, rc, status, exit_code):
    hub, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(rc, "{'inserted': 1}"))
    r = patrol._step_build_vectors(hub, engine)
    assert r.status == status and r.exit_code == exit_code


def test_router_sync_skips_when_script_missing(patrol_tree):
    hub, engine = patrol_tree
    r = patrol._step_router_sync(hub, engine)
    assert r.status == "skip" and r.exit_code == 0


def test_router_sync_nonzero_is_warn(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    _touch(engine, "router_sync.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "", "路由表漂移"))
    r = patrol._step_router_sync(hub, engine)
    assert r.status == "warn" and "路由表漂移" in r.output


# ---------------------------------------------------------------------------
# 数据质量
# ---------------------------------------------------------------------------


def test_vector_regression_missing_bench_skips(patrol_tree):
    hub, engine = patrol_tree
    assert patrol._step_vector_regression(hub, engine).status == "skip"


def test_vector_regression_passes_fail_below_threshold(patrol_tree, monkeypatch):
    """回归：`--fail-below 0.8` 曾被遗漏 ⇒ 命中率 50% 也判 PASS（门禁形同虚设）。"""
    hub, engine = patrol_tree
    _touch(engine, "vector_bench.py")
    fake = FakeCmd(0, "命中率 100%")
    monkeypatch.setattr(patrol_steps, "_run_cmd", fake)
    r = patrol._step_vector_regression(hub, engine)
    assert r.status == "pass"
    assert "--fail-below" in fake.last["argv"] and "0.8" in fake.last["argv"]


def test_vector_regression_below_threshold_is_warn(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    _touch(engine, "vector_bench.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(2, "命中率 65% < 0.8"))
    r = patrol._step_vector_regression(hub, engine)
    assert r.status == "warn" and r.exit_code == 2


def test_metrics_daily_skip_and_warn(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    assert patrol._step_metrics_daily(hub, engine).status == "skip"
    _touch(engine, "metrics_daily.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "", "聚合失败"))
    r = patrol._step_metrics_daily(hub, engine)
    assert r.status == "warn" and "聚合失败" in r.output


def test_hub_review_skip_and_pass(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    assert patrol._step_hub_review(hub, engine).status == "skip"
    _touch(engine, "hub_review_today.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, "待审 3 张"))
    r = patrol._step_hub_review(hub, engine)
    assert r.status == "pass" and "待审 3 张" in r.output


# ---------------------------------------------------------------------------
# 报告归档
# ---------------------------------------------------------------------------


def test_status_snapshot_requires_valid_json(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, "not-json"))
    assert patrol._step_status_snapshot(hub, engine).status == "fail"

    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(2, json.dumps({"cards": 1})))
    r = patrol._step_status_snapshot(hub, engine)
    assert r.status == "pass" and r.exit_code == 2  # exit=2（有告警）仍算快照可用


def test_archive_snapshot_writes_retro_file(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, json.dumps({"cards": {"rules": 3}})))
    r = patrol._save_snapshot_archive(hub, engine)
    today = datetime.now(_CN_TZ).date().isoformat()
    snap = hub / "retro" / f"snapshot-{today}.json"
    assert r.status == "pass" and snap.is_file()
    assert json.loads(snap.read_text(encoding="utf-8"))["cards"]["rules"] == 3


def test_archive_snapshot_no_overwrite_is_idempotent(patrol_tree, monkeypatch):
    """同日快照已存在 ⇒ 跳过覆盖（幂等保护，防手滑重跑覆盖基线）。"""
    hub, engine = patrol_tree
    today = datetime.now(_CN_TZ).date().isoformat()
    snap = hub / "retro" / f"snapshot-{today}.json"
    snap.write_text(json.dumps({"generated_at": f"{today}T08:00:00+08:00"}), encoding="utf-8")

    fake = FakeCmd(0, json.dumps({"cards": {}}))
    monkeypatch.setattr(patrol_steps, "_run_cmd", fake)
    r = patrol._save_snapshot_archive(hub, engine, no_overwrite=True)
    assert r.status == "pass" and "幂等保护" in r.output
    assert fake.calls == [], "幂等命中时不应再调子进程"


def test_archive_snapshot_broken_existing_file_is_overwritten(patrol_tree, monkeypatch):
    """存在但损坏 ⇒ 允许覆盖（否则坏基线永久卡死归档）。"""
    hub, engine = patrol_tree
    today = datetime.now(_CN_TZ).date().isoformat()
    (hub / "retro" / f"snapshot-{today}.json").write_text("{ 坏 json", encoding="utf-8")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, json.dumps({"cards": {}})))
    r = patrol._save_snapshot_archive(hub, engine, no_overwrite=True)
    assert r.status == "pass" and "已归档" in r.output


# ---------------------------------------------------------------------------
# 自动修复层
# ---------------------------------------------------------------------------


def test_auto_fix_lint_skip_and_warn(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    assert patrol._step_auto_fix_lint(hub, engine).status == "skip"
    _touch(engine, "auto_fix_lint.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "修复 0 张", ""))
    assert patrol._step_auto_fix_lint(hub, engine).status == "warn"


def test_auto_pytest_env_fix_never_fails_patrol(patrol_tree, monkeypatch):
    """修复步骤失败只降为 warn（exit_code 归 0），不把巡检判红。"""
    hub, engine = patrol_tree
    _touch(engine, "auto_pytest_env_fix.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "修不了"))
    r = patrol._step_auto_pytest_fix(hub, engine)
    assert r.status == "warn" and r.exit_code == 0


def test_auto_pytest_env_fix_outer_timeout_exceeds_inner(patrol_tree, monkeypatch):
    """外层 420s 必须 > 内层 pytest 180s（曾因外 120s < 内 ⇒ 内层永不生效）。"""
    hub, engine = patrol_tree
    _touch(engine, "auto_pytest_env_fix.py")
    fake = FakeCmd(0, "ok")
    monkeypatch.setattr(patrol_steps, "_run_cmd", fake)
    patrol._step_auto_pytest_fix(hub, engine)
    assert fake.last["timeout"] >= 420


@pytest.mark.parametrize("step_name", ["auto_sleep_filter", "auto_process_sleep"])
def test_sleep_autofix_passes_three_day_window(patrol_tree, monkeypatch, step_name):
    """sleep 类修复只看近 3 天（窗口写错会扫全量、把老候选反复翻出来）。"""
    hub, engine = patrol_tree
    _touch(engine, f"{step_name}.py")
    fake = FakeCmd(0, "处理 2 条")
    monkeypatch.setattr(patrol_steps, "_run_cmd", fake)
    fn = getattr(patrol, f"_step_{step_name}")
    r = fn(hub, engine)
    assert r.status == "pass"
    assert fake.last["argv"][-2:] == ["--since-days", "3"]


def test_auto_review_today_skip_and_pass(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    assert patrol._step_auto_review_today(hub, engine).status == "skip"
    _touch(engine, "auto_review_today.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, "过审 4 张"))
    r = patrol._step_auto_review_today(hub, engine)
    assert r.status == "pass" and "过审 4 张" in r.output


# ---------------------------------------------------------------------------
# 修复验证 / 新鲜度 / 平台层
# ---------------------------------------------------------------------------


def test_verify_after_fix_fails_when_any_check_fails(patrol_tree, monkeypatch):
    _, engine = patrol_tree
    monkeypatch.setattr(subprocess, "run", FakeRun(0, "passed"))
    assert patrol._step_verify_after_fix(engine, {}).status == "pass"

    monkeypatch.setattr(subprocess, "run", FakeRun(1, "1 failed"))
    r = patrol._step_verify_after_fix(engine, {})
    assert r.status == "fail" and r.exit_code == 1 and "pytest_smoke" in r.output


def test_freshness_check_skip_when_script_missing(patrol_tree):
    hub, engine = patrol_tree
    r = patrol._step_freshness_check(hub, engine)
    assert r.status == "skip" and r.exit_code == 0


def test_freshness_check_result_always_carries_stage(patrol_tree, monkeypatch):
    """回归：漏传 stage 会被 _run_step 兜底成 exit_code=999 的假故障。"""
    hub, engine = patrol_tree
    _touch(engine, "stale_detect.py")
    monkeypatch.setattr(subprocess, "run", FakeRun(0, "0 张陈旧"))
    r = patrol._run_step("freshness_check", "新鲜度", lambda: patrol._step_freshness_check(hub, engine))
    assert r.exit_code == 0 and r.status == "pass" and r.stage == "新鲜度"


def test_freshness_check_timeout_is_fail(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    _touch(engine, "stale_detect.py")
    monkeypatch.setattr(subprocess, "run", FakeRun(raise_timeout=True))
    r = patrol._step_freshness_check(hub, engine)
    assert r.status == "fail" and r.output == "timeout"


def test_platform_sync_drift_is_fail_exit1(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    assert patrol._step_platform_sync_check(hub, engine).status == "skip"
    _touch(engine, "platform_sync.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "❌ trae 需同步", ""))
    r = patrol._step_platform_sync_check(hub, engine)
    assert r.status == "fail" and r.exit_code == 1 and "需同步" in r.output


def test_platform_healthcheck_lists_non_green(patrol_tree, monkeypatch):
    hub, engine = patrol_tree
    _touch(engine, "platform_healthcheck.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(1, "trae RED 会话超时", ""))
    r = patrol._step_platform_healthcheck(hub, engine)
    assert r.status == "fail" and r.exit_code == 1 and "RED" in r.output


def test_platform_unregistered_is_informational_only(patrol_tree, monkeypatch):
    """未接入平台提示恒为 pass（信息级，不制造红灯）。"""
    hub, engine = patrol_tree
    _touch(engine, "platform_unregistered.py")
    monkeypatch.setattr(patrol_steps, "_run_cmd", FakeCmd(0, "• cursor\n• windsurf", ""))
    r = patrol._step_platform_unregistered(hub, engine)
    assert r.status == "pass" and r.exit_code == 0 and "2 个候选待接入" in r.output
