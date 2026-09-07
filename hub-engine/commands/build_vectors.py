# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 build_vectors（engine.py P1 拆分）
"""CLI 子命令：`hub build_vectors` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_build_vectors(args) -> int:
    from tools.semsearch import build

    stats = build(Path(args.root))
    print(stats)
    touched = stats["inserted"] + stats["updated"] + stats["reused"]
    if touched > 0 and stats["embedded"] + stats["reused"] == 0:
        print(
            "【告警】向量通道退化：有卡片处理但零向量（embed 后端/模型/网络不可用），"
            "语义检索已回退词袋，请检查 bge 模型与网络。"
        )
        return 2
    return 0

