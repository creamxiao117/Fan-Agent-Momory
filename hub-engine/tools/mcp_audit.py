# @version V1.1 / 2026-09-07 / Hermes / 统一记忆中枢 query.log 审计追加 + 按日切分
"""MCP 审计日志：query.log 按日切分（Asia/Shanghai 0 点切换）+ 多文件读取

写入侧：按本地日期分文件 `query.log-YYYY-MM-DD.jsonl`。
读取侧：`query_log_files(root)` glob 全部历史日志，兼容 `query.log.jsonl` 老格式。

V1.1 (2026-09-07): 按日切分 + 兼容老格式 + 提供 query_log_files() 列出。
V1.0 (2026-08): 单一 query.log.jsonl 8MB rotate-by-bytes。
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai
LEGACY_LOG = "query.log.jsonl"            # 历史单一文件（向后兼容）
LOG_PREFIX = "query.log-"                # 按日切分文件前缀
LOG_SUFFIX = ".jsonl"

# 旧版的 8MB 字节级 rotate 仍保留作为最后兜底（单日极端情况）
ROTATE_BYTES = 8 * 1024 * 1024


def _ts() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _today_str() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def audit_id() -> str:
    """形如 20260818T153012Z-a1b2c3d4（8 位 hex 随机段，避免同秒碰撞）"""
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )


def _state_dir(root: Path) -> Path:
    return root / ".sync" / "state"


def _daily_path(d: Path) -> Path:
    """今日按日切分日志路径"""
    return d / f"{LOG_PREFIX}{_today_str()}{LOG_SUFFIX}"


def query_log_files(root: Path) -> list[Path]:
    """列出全部 query.log 文件，按日期排序（最新在前）。

    包含：
    - query.log.jsonl（旧版单一文件，如存在）
    - query.log-YYYY-MM-DD.jsonl（按日切分）
    """
    d = _state_dir(root)
    if not d.is_dir():
        return []
    out: list[Path] = []
    legacy = d / LEGACY_LOG
    if legacy.is_file():
        out.append(legacy)
    out.extend(sorted(d.glob(f"{LOG_PREFIX}*{LOG_SUFFIX}"), reverse=True))
    return out


def append_query_log(root: Path, record: dict) -> None:
    """best-effort 追加一行；按本地日期写入 `query.log-YYYY-MM-DD.jsonl`。

    目录/写盘失败静默（不阻断业务）。
    """
    try:
        d = _state_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        path = _daily_path(d)

        # 字节级兜底 rotate（单日极端超 8MB 时切新文件）
        if path.exists() and path.stat().st_size > ROTATE_BYTES:
            path.rename(
                d / f"{LOG_PREFIX}{_today_str()}-{datetime.now(timezone.utc).strftime('%H%M%S')}{LOG_SUFFIX}"
            )

        rec = {"ts": _ts(), **record}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass