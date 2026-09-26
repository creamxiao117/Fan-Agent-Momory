# @version V1.1 / 2026-09-26 / Hermes + pi / T15 改进工具统一编排入口
"""hub_orchestrator.py - T15 6 工具统一 cron 入口.

V1.0 (2026-09-09): 6 项 cron 任务统一调度。
V1.1 (2026-09-26): 补回 **sys.path 引导**（回归修复）。
    P1-c 把写死盘符路径换成 `from common.config import external_path` 时，忘了这个
    脚本此前是靠 cwd/env 才导得到 `common` 的 ⇒ Hermes cron（working dir 不是
    hub-engine）下抛 `ModuleNotFoundError: No module named 'common'`，
    2026-09-26 06:00 真的挂了一场。护栏：tests/test_script_bootstrap.py。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.config import external_path  # noqa: E402

# SkillHub 检出根：env SKILLHUB_ROOT → hub.config.yaml:external_paths.skillhub → 内置默认
# （原为在 3 条命令里各写死一次盘符路径；收敛为**单点**，换机只改一处）
_REPO = Path(__file__).resolve().parents[2]
_SKILLHUB = external_path("skillhub", _REPO / "AgentMemoryHub")
SKILLHUB_ROOT = str(_SKILLHUB) if _SKILLHUB else ""

# 工具清单（task_name, subprocess args list, timeout_seconds）
TASKS = [
    (
        "skill_health",
        [
            "python",
            "-c",
            (
                "import sys; sys.path.insert(0, 'router'); "
                "from pathlib import Path; "
                "from tools.skill_health import scan_skillhub, summarize; "
                "r = scan_skillhub(Path('.')); s = summarize(r); "
                "print('avg:', s['avg_score'], 'low_health:', len(s['low_health']))"
            ),
        ],
        60,
    ),
    (
        "llm_route",
        [
            "python",
            "-c",
            (
                "import sys; sys.path.insert(0, 'router'); "
                "from tools.route_with_llm import route_with_llm; "
                "r = route_with_llm('router/router.yaml', '写一个开发计划'); "
                "print('llm_route hits:', [h['name'] for h in r])"
            ),
        ],
        30,
    ),
    (
        "stale_detect",
        [
            "python",
            "hub-engine/scripts/stale_detect.py",
            "--hub-root",
            ".",
            "--skillhub-root",
            SKILLHUB_ROOT,
            "--days",
            "60",
        ],
        30,
    ),
    (
        "knowledge_gap",
        [
            "python",
            "hub-engine/scripts/knowledge_gap.py",
            "--hub-root",
            ".",
            "--hours",
            "24",
        ],
        30,
    ),
    (
        "skill_candidate",
        [
            "python",
            "hub-engine/scripts/skill_candidate_suggest.py",
            "--hub-root",
            ".",
            "--skillhub-root",
            SKILLHUB_ROOT,
            "--threshold",
            "3",
        ],
        30,
    ),
    (
        "freshness",
        [
            "python",
            "hub-engine/scripts/stale_detect.py",
            "--hub-root",
            ".",
            "--skillhub-root",
            SKILLHUB_ROOT,
            "--days",
            "90",
        ],
        30,
    ),
]


def run_task(task_name, args, timeout, hub_root, skillhub_root):
    """执行 1 个子任务。返回 (returncode, info_dict)。"""
    print(f"[1/6] {task_name}")
    args_str = str(args)
    use_skillhub = "tools." in args_str or "tools/" in args_str or "router/" in args_str
    cwd = skillhub_root if use_skillhub else hub_root
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        out = r.stdout.strip()[:200]
        err = r.stderr.strip()[:200]
        if r.returncode == 0:
            print(f"  OK: {out}")
        else:
            print(f"  FAIL({r.returncode}): {out} {err}")
        info = {"stdout": out, "stderr": err, "returncode": r.returncode}
        return r.returncode, info
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s")
        return 1, {"stdout": "", "stderr": f"timeout after {timeout}s", "returncode": 1}


def main():
    ap = argparse.ArgumentParser(description="hub_orchestrator")
    ap.add_argument("--hub-root", required=True)
    ap.add_argument("--skillhub-root", required=True)
    ap.add_argument("--fan-root", required=True, help="Fan-Agent-Momory 根（含 hub-engine/）")
    ap.add_argument("--task", help="单任务运行（默认全部）")
    args = ap.parse_args()

    hub_root = str(Path(args.hub_root).resolve())
    skillhub_root = str(Path(args.skillhub_root).resolve())
    fan_root = str(Path(args.fan_root).resolve())

    # 把所有命令中的 hub-engine/scripts/xxx.py 替换为 fan_root/hub-engine/scripts/xxx.py
    # --hub-root 从 . 替换为 hub_root 绝对路径
    resolved_tasks = []
    for name, cmd_args, timeout in TASKS:
        new_args = []
        for a in cmd_args:
            if isinstance(a, str) and a.startswith("hub-engine/scripts/"):
                new_args.append(str(Path(fan_root) / a))
            elif a == "..":
                # 把 ".." 替换为 hub_root 的父目录
                new_args.append(str(Path(hub_root).parent))
            elif a == ".":
                new_args.append(hub_root)
            else:
                new_args.append(a)
        resolved_tasks.append((name, new_args, timeout))

    failed = 0
    results: dict = {}
    for task_name, cmd_args, timeout in resolved_tasks:
        if args.task and args.task != task_name:
            continue
        rc, info = run_task(task_name, cmd_args, timeout, hub_root, skillhub_root)
        failed += rc
        results[task_name] = {"ok": rc == 0, "info": info}

    # 写 6 面板结果 JSON 供飞轮日报消费（叠加不删，可观测）
    out_dir = Path(hub_root) / "system" / "run"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "daily-6panel.json"
    try:
        out_path.write_text(
            json.dumps(
                {
                    "generated_at": _iso_now(),
                    "hub_root": hub_root,
                    "skillhub_root": skillhub_root,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n[orchestrator] 6 面板结果已写: {out_path}")
    except OSError as exc:
        print(f"\n[orchestrator] 写 JSON 失败: {exc}", file=sys.stderr)

    print(f"\n=== 汇总: {len(TASKS)} 任务, 失败 {failed} ===")
    return 0 if failed == 0 else 1


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.exit(main())
