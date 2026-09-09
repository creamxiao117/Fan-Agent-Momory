# @version V1.0 / 2026-09-09 / Hermes / T15 改进工具统一编排入口
"""hub_orchestrator.py - T15 6 工具统一 cron 入口.

V1.0 (2026-09-09): 6 项 cron 任务统一调度。
"""

import argparse
import subprocess
import sys
from pathlib import Path

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
            "D:/AIwork/20260821-Fan-SkillHub",
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
            "D:/AIwork/20260821-Fan-SkillHub",
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
            "D:/AIwork/20260821-Fan-SkillHub",
            "--days",
            "90",
        ],
        30,
    ),
]


def run_task(task_name, args, timeout, hub_root, skillhub_root):
    print(f"[1/6] {task_name}")
    args_str = str(args)
    use_skillhub = "tools." in args_str or "tools/" in args_str or "router/" in args_str
    cwd = skillhub_root if use_skillhub else hub_root
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        out = r.stdout.strip()[:200]
        err = r.stderr.strip()[:200]
        if r.returncode == 0:
            print(f"  OK: {out}")
        else:
            print(f"  FAIL({r.returncode}): {out} {err}")
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s")
        return 1


def main():
    ap = argparse.ArgumentParser(description="hub_orchestrator")
    ap.add_argument("--hub-root", required=True)
    ap.add_argument("--skillhub-root", required=True)
    ap.add_argument(
        "--fan-root", required=True, help="Fan-Agent-Momory 根（含 hub-engine/）"
    )
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
    for task_name, cmd_args, timeout in resolved_tasks:
        if args.task and args.task != task_name:
            continue
        rc = run_task(task_name, cmd_args, timeout, hub_root, skillhub_root)
        failed += rc

    print(f"\n=== 汇总: {len(TASKS)} 任务, 失败 {failed} ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
