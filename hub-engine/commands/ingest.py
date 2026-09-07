# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 ingest（engine.py P1 拆分）
"""CLI 子命令：`hub ingest` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_ingest(args) -> int:
    from common.config import load_engine_config
    from engine import chat, smart_chat  # lazy: 避免循环导入
    from sync import ingest

    cfg = load_engine_config()
    batch_model = str(cfg.get("batch_model", "") or "").strip()
    chat_fn = (
        (lambda prompt, root: smart_chat(prompt, root))
        if batch_model
        else chat
    )
    stat = ingest(Path(args.root), args.platform, chat_fn=chat_fn)
    print(stat)
    return 0 if stat["status"] == "ok" else 1

