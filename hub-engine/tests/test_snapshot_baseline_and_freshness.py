# @version V1.0 / 2026-09-15 / Hermes / 巡检快照基线解包 + 步骤 stage 必填的回归断言
"""回归断言：2026-09-15 修复的两类缺陷不得复发。

缺陷 A（快照基线恒 0）：
    `patrol_runner.py` 把报告写到 `--output`，而该路径与归档步骤
    `retro/snapshot-<date>.json` 相同 → 落盘的是**外层包装**
    （{"stages": [...], "snapshot": {扁平快照}, "alerts": [...]}）。
    旧 `load_previous_snapshot` 直接取顶层 → `prev.get("cards")` 恒空
    → 对比里 prev 全 0（表现为"卡片 0→87"的假增量）。

缺陷 B（freshness_check 假故障）：
    `_step_freshness_check` 构造 `StepResult` 漏传必填的 `stage`
    → TypeError 被 `_run_step` 兜底成 exit_code=999 的 fail
    → 直接推高整体退出码（契约误判为"需关注"）。
"""

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from commands.status import compare_snapshots, load_previous_snapshot

_CN_TZ = timezone(timedelta(hours=+8))
_ENGINE_DIR = Path(__file__).resolve().parent.parent


def _yesterday() -> str:
    return (datetime.now(_CN_TZ) - timedelta(days=1)).date().isoformat()


def _write_prev_snapshot(root: Path, payload: dict) -> Path:
    retro = root / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    path = retro / f"snapshot-{_yesterday()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 缺陷 A：快照基线
# ---------------------------------------------------------------------------


def test_load_previous_snapshot_unwraps_patrol_wrapper(tmp_path):
    """patrol 外层包装形态必须被解包成扁平快照（cards 在顶层）。"""
    _write_prev_snapshot(
        tmp_path,
        {
            "hub_root": str(tmp_path),
            "generated_at": "2026-09-14T16:17:00+08:00",
            "stages": [{"name": "基础设施", "steps": []}],
            "snapshot": {
                "cards": {"blueprints": 84, "rules": 28},
                "health_scores": {"overall": 72.0},
            },
            "alerts": [{"level": "warning", "rule": "lint_issues", "message": "x"}],
        },
    )

    prev = load_previous_snapshot(tmp_path)

    assert prev is not None
    # 核心断言：解包后顶层能看到 cards（旧实现此处恒为 {}）
    assert prev["cards"] == {"blueprints": 84, "rules": 28}
    assert prev["health_scores"]["overall"] == 72.0
    # 仅存在于外层的 alerts 需回填，否则"新增/消除告警"对比失效
    assert prev["alerts"][0]["rule"] == "lint_issues"


def test_load_previous_snapshot_flat_passthrough(tmp_path):
    """扁平形态（engine status 直出）保持原样返回，不被误解包。"""
    _write_prev_snapshot(tmp_path, {"cards": {"rules": 29}, "alerts": []})

    prev = load_previous_snapshot(tmp_path)

    assert prev is not None
    assert prev["cards"] == {"rules": 29}


def test_load_previous_snapshot_missing_returns_none(tmp_path):
    assert load_previous_snapshot(tmp_path) is None


def test_load_previous_snapshot_corrupt_returns_none(tmp_path):
    retro = tmp_path / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    (retro / f"snapshot-{_yesterday()}.json").write_text("{not json", encoding="utf-8")

    assert load_previous_snapshot(tmp_path) is None


def test_compare_snapshots_reads_wrapper_baseline(tmp_path):
    """端到端：包装形态的昨日快照 → 对比结果 prev 不得为 0。"""
    _write_prev_snapshot(
        tmp_path,
        {
            "snapshot": {
                "cards": {"blueprints": 84, "rules": 28},
                "health_scores": {"overall": 72.0},
            },
            "alerts": [],
        },
    )
    prev = load_previous_snapshot(tmp_path)
    curr = {
        "cards": {"blueprints": 90, "rules": 29},
        "health_scores": {"overall": 71.9},
        "alerts": [],
    }

    changes = compare_snapshots(prev, curr)

    assert changes["cards"]["blueprints"] == {
        "delta": 6,
        "prev": 84,
        "curr": 90,
    }
    assert changes["cards"]["rules"]["prev"] == 28


# ---------------------------------------------------------------------------
# 缺陷 B：StepResult.stage 必填
# ---------------------------------------------------------------------------


def test_all_stepresult_constructions_pass_stage():
    """静态门禁：patrol_runner.py 内所有 StepResult(...) 必须传 stage。

    这是"类级"断言——修复单点后，新增步骤若再漏传 stage 会被本测试直接拦下。
    """
    src = (_ENGINE_DIR / "scripts" / "patrol_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    missing: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Name) and fn.id == "StepResult"):
            continue
        kw_names = {kw.arg for kw in node.keywords}
        # name/stage/status 三个必填项中，stage 必须显式给出（位置实参 ≥2 也算）
        if "stage" not in kw_names and len(node.args) < 2:
            missing.append(node.lineno)

    assert missing == [], f"以下 StepResult 构造漏传 stage: 行 {missing}"


def test_freshness_check_step_is_callable_without_exception(tmp_path):
    """freshness_check 步骤必须正常返回 StepResult（不得抛 TypeError）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_patrol_runner_probe", _ENGINE_DIR / "scripts" / "patrol_runner.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # script 缺失分支：应返回 skip 且带 stage，而不是抛异常
    result = mod._step_freshness_check(tmp_path, tmp_path)

    assert result.stage, "StepResult.stage 不得为空"
    assert result.status in {"pass", "fail", "skip", "warn"}
    assert result.exit_code != 999, "999 仅在 _run_step 兜底异常时出现"
