"""CLI 子命令包：每个模块对应 engine.py 的一个子命令。

V1.0 (2026-09-07): engine.py 拆分——从 44KB 单文件按子命令拆出。

说明：chat 命令不拆——smart_chat + 5 个 chat helpers 共享性高，
      单文件分拆破坏性大，留 engine.py。
"""

from commands.build_vectors import cmd_build_vectors
from commands.confirm import cmd_confirm
from commands.distill import cmd_distill
from commands.gate import cmd_gate
from commands.ingest import cmd_ingest
from commands.lint import cmd_lint
from commands.retrieve import cmd_retrieve
from commands.status import cmd_status
from commands.sync import cmd_sync
from commands.tidy import cmd_tidy

__all__ = [
    "cmd_build_vectors",
    "cmd_confirm",
    "cmd_distill",
    "cmd_gate",
    "cmd_ingest",
    "cmd_lint",
    "cmd_retrieve",
    "cmd_status",
    "cmd_sync",
    "cmd_tidy",
]
