# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 tidy（engine.py P1 拆分）
"""CLI 子命令：`hub tidy` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_tidy(args) -> int:
    from tools.tidy import archive

    dst = archive(Path(args.root), args.rel, reason=args.reason)
    print(f"已归档: {dst}")
    return 0

