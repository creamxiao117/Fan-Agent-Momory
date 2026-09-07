# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 audit
"""CLI 子命令：hub audit INDEX 自动审核。

V1.0 (2026-09-07): T7 L2 巡检新增 - INDEX 一致性 + 格式 + 重复检查。
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_audit(args) -> int:
    script = Path(__file__).resolve().parent.parent / "scripts" / "audit_index.py"
    cmd = [sys.executable, str(script), "--root", str(args.root)]
    if getattr(args, "report", False):
        cmd.append("--report")
    if getattr(args, "no_fail", False):
        cmd.append("--no-fail")
    r = subprocess.run(cmd, capture_output=False, text=True, encoding="utf-8")
    return r.returncode