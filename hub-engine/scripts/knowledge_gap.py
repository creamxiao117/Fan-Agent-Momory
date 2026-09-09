# @version V1.0 / 2026-09-09 / Hermes / 知识缺口检测脚本
"""knowledge_gap.py - 读取 query.log.jsonl 统计未命中查询.

V1.0 (2026-09-09): 替代 hub_orchestrator.py 中的 -c inline python。
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LOG = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-root", default=".")
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()

    log = Path(args.hub_root) / ".sync" / "state" / "query.log.jsonl"
    if not log.exists():
        print(f"log not found: {log}")
        return 1
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    total = miss = 0
    miss_q = {}
    for line in log.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            _LOG.debug("skip bad json line: %s", exc)
            continue
        ts = e.get("ts", 0)
        if isinstance(ts, (int, float)):
            entry_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            continue
        if entry_time < cutoff:
            continue
        if e.get("action") not in ("search", "retrieve"):
            continue
        total += 1
        if e.get("hit_count", 0) == 0:
            miss += 1
            q = (e.get("query") or "").strip()
            if q:
                miss_q[q] = miss_q.get(q, 0) + 1
    rate = (miss / total * 100) if total else 0
    top = sorted(miss_q.items(), key=lambda x: -x[1])[:3]
    print(f"gap: {miss}/{total} ({rate:.1f}%)")
    for q, c in top:
        print(f"  top: {q[:40]} ({c})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
