# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 retrieve（engine.py P1 拆分）
"""CLI 子命令：`hub retrieve` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.retrieve import retrieve


def cmd_retrieve(args) -> int:
    for c in retrieve(
        Path(args.root), args.query, top_k=args.top_k, n=args.n, mode=args.mode
    ):
        from tools.snippet import extract_snippet

        print(f"[{c.type}/{c.status}] {c.path.name}")
        print(extract_snippet(c.body, args.query))
    return 0

