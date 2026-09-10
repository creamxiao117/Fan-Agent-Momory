# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 sync（engine.py P1 拆分）
"""CLI 子命令：`hub sync` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import HubConfig


def cmd_sync(args) -> int:
    from tools.platform_bridge import pull, push

    root = Path(args.root)
    cfg = HubConfig.load(root)
    platforms = list(cfg.platforms) if args.platform == "all" else [args.platform]
    ok = True
    for name in platforms:
        try:
            stat = (
                push(
                    root,
                    name,
                    only_rules=args.only_rules,
                    name_filter=args.name,
                    dry_run=args.dry_run,
                )
                if args.push
                else pull(root, name, dry_run=args.dry_run)
            )
        except KeyError as e:
            print(e)
            ok = False
            continue
        print(f"{name}: {stat}")
        ok = ok and stat["status"] == "ok"
    return 0 if ok else 1
