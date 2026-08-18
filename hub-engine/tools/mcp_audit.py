"""MCP 审计日志：query.log.jsonl（best-effort 追加 + 简单轮转）"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_NAME = "query.log.jsonl"
ROTATE_BYTES = 8 * 1024 * 1024


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit_id() -> str:
    """形如 20260818T153012Z-a1b2c3d4（8 位 hex 随机段，避免同秒碰撞）"""
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )


def append_query_log(root: Path, record: dict) -> None:
    """best-effort 追加一行；目录/写盘失败静默（不阻断业务）"""
    try:
        d = root / ".sync" / "state"
        d.mkdir(parents=True, exist_ok=True)
        path = d / LOG_NAME
        if path.exists() and path.stat().st_size > ROTATE_BYTES:
            path.rename(
                path.with_name(
                    f"{LOG_NAME}.{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                )
            )
        rec = {"ts": _ts(), **record}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass
