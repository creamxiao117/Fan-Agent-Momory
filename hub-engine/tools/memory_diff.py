"""结构化记忆变更审计（OpenViking 路径 C 落地）：memory_diff.jsonl。

每次写回（ingest）在写路径同步产一条结构化变更记录，落
`.sync/state/memory_diff.jsonl`（与 read 侧 query.log 同源目录，write 侧可核）。
对齐 OpenViking memory_diff.json 语义：
- add    → {op, name, type, before: null, after: dest 相对路径}
- update → {op, name, type, before, after, diff 摘要}
- delete → {op, name, type, deleted_content 摘要}（冲突区回收等）
- 空操作 → 写零计数 {op: "noop"} 结构（OpenViking 空操作也给零计数空结构）

纯追加、幂等、异常不抛（写 diff 失败绝不阻断写回主流程）。与 read 侧
query.log（mcp_audit.action=writeback）组合 = 同源可核：query.log 记「有过写回」，
memory_diff 记「写了什么 before/after」。
"""

import json
import os
from pathlib import Path

_STATE = Path(".sync") / "state"
LOG_NAME = "memory_diff.jsonl"


def _log_path(root: Path) -> Path:
    return Path(root) / _STATE / LOG_NAME


def record(root: Path, operation: dict) -> Path | None:
    """追加一条结构化变更记录；返回日志路径（失败返回 None 且不抛错）。

    operation 须含 `op`（add/update/delete/noop）。其余字段（name/type/before/
    after/deleted_content）随语义酌情携带。best-effort：任何异常静默降级。
    """
    op = operation.get("op", "noop")
    record_ = {"op": op}
    record_.update({k: v for k, v in operation.items() if k != "op"})
    try:
        path = _log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_, ensure_ascii=False) + os.linesep)
            f.flush()  # 幂等追加后立即落盘，保证 write 侧可核
        return path
    except OSError:  # 审计失败不阻断写回主流程
        return None


def read_records(root: Path) -> list[dict]:
    """读全部变更记录（容忍残行），供 read 侧消费/巡检。"""
    path = _log_path(root)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:  # 容忍残行
            continue
    return out