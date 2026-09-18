# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 lint（engine.py P1 拆分）
"""CLI 子命令：`hub lint` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_lint(args) -> int:
    from tools.lint import lint

    report = lint(Path(args.root))
    print("孤儿页:", report["orphans"])
    print("幽灵登记:", report["ghosts"])
    print("hook漂移:", [h["name"] for h in report["hooks"]])
    print("陈旧页:", report["stale"])
    print("无效卡片:", report["invalid"])
    drift = report["schema_drift"]
    print("非权威区漂移:", [f"{d['dir']}/{d['name']}" for d in drift])
    tdm = report.get("type_dir_mismatch", [])
    print(
        "type↔目录:",
        [f"{d['dir']}/{d['name']}({d['type']}≠{d['expected']})" for d in tdm],
    )
    print("备注:", report["notes"])
    unhealthy = (
        len(report["orphans"])
        + len(report["ghosts"])
        + len(report["stale"])
        + report["invalid"]
        + len(drift)
        + len(tdm)
    )
    if unhealthy:
        print(
            f"【告警】发现 {unhealthy} 处健康问题：orphans {len(report['orphans'])} / "
            f"ghosts {len(report['ghosts'])} / stale {len(report['stale'])} / invalid {report['invalid']} / "
            f"schema_drift {len(drift)} / type_dir {len(tdm)}"
        )
        return 2
    return 0
