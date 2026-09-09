# @version V1.0 / 2026-09-09 / Hermes / Dashboard daily regenerate (T5)
"""dashboard_regen - 中枢总控台 dashboard 每日重生成.

V1.0 (2026-09-09): 任务 5 (T5) — 每天 7:00 跑:
1. 跑 T3 dashboard_collect.py 生成 dashboard-data.json
2. 复制 T1 mockup.html 到 T4 dashboard.html
3. 复制 data 到 T4 目录
注: T4 的 JS 已集成在 T1 mockup 阶段; 此脚本只更新数据。
"""
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv")
SLOTS = BASE / "work/dashboard/slots"
T1 = SLOTS / "T1-mockup"
T3 = SLOTS / "T3-collect"
T4 = SLOTS / "T4-integration"

def main():
    # 1. 跑 T3 数据采集
    r = subprocess.run(
        [sys.executable, str(T3 / "dashboard_collect.py"),
         "--hub-root", str(BASE / "AgentMemoryHub"),
         "--skillhub-root", r"D:/AIwork/20260821-Fan-SkillHub"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"T3 failed: {r.stderr}", file=sys.stderr)
        return 1
    # 2. 复制 data
    shutil.copy(T3 / "dashboard-data.json", T4 / "dashboard-data.json")
    # 3. 仅复制 data（dashboard.html 由 T4 维护，不覆盖）
    # 注：T4 已自包含 data URL 嵌入，regen 只更新 data 文件
    print(f"dashboard regenerated at {T4 / 'dashboard.html'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
