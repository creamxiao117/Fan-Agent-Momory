"""E1 指标日行：把中枢成长度量落成时间序列（飞轮 E 环·可验证信号）。

产出 `.sync/state/metrics.jsonl`——append-only，一行/日，字段：
  - date          本地日期（YYYY-MM-DD）
  - total_cards   权威区卡片数（复用 tools.lint 遍历，含 blueprints）
  - vector_rows   向量库 .sync/vector.db 行数（无库记 0）
  - search_count  当日查询次数（query.log action==search 计数）
  - hit           当日命中查询数（hit_count>0）
  - miss          当日未命中查询数（hit_count==0）
  - hit_rate      命中率 hit/search_count（无查询记 null）
  - reuse_ops     当日复用操作数（query.log action==reuse 计数，A2 落地后填充）

只读聚合 + 追加写 metrics.jsonl，不修改 query.log / 卡片。纳入每日巡检 append。

用法：
  python hub-engine/scripts/metrics_daily.py --root AgentMemoryHub            # 本地今天，追加一行
  python hub-engine/scripts/metrics_daily.py --root AgentMemoryHub --date 2026-08-19
  python hub-engine/scripts/metrics_daily.py --root AgentMemoryHub --json     # 只输出本次行，不落盘
"""

import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"
METRICS = Path(".sync") / "state" / "metrics.jsonl"
LOG_DIR = Path(".sync") / "state"
LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai
_AUTHORITY_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "experience",
    "libs",
    "retro",
    "blueprints",
)


def _today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def _local_date_of(ts_utc: str | None) -> date:
    """query.log `ts` 为 UTC ISO（如 2026-08-19T15:22:00Z）；转本地 +8 后取日期。"""
    if not ts_utc:
        return _today_local()
    try:
        dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        return dt.astimezone(LOCAL_TZ).date()
    except ValueError:
        return _today_local()


def load_records(root: Path) -> list[dict]:
    """复用 missing_query 的解析层：容忍残行，不抛异常。"""
    log = Path(root) / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _vector_rows(root: Path) -> int:
    db = Path(root) / ".sync" / "vector.db"
    if not db.exists():
        return 0
    try:
        con = sqlite3.connect(str(db))
        try:
            return int(con.execute("SELECT COUNT(*) FROM docs").fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def _total_cards(root: Path) -> int:
    # 权威区目录与 tools.lint.AUTHORITY_DIRS 保持一致；脚本自包含，避免依赖包导入路径。
    n = 0
    for sub in _AUTHORITY_DIRS:
        d = Path(root) / sub
        if not d.exists():
            continue
        for p in d.glob("*.md"):
            if p.name == "log.md" or p.name.startswith("lint-report-"):
                continue
            n += 1
    return n


def compute(root: Path, when: date | None = None) -> dict:
    """聚合指定日期（默认本地今天）的 query.log → 一行指标。"""
    when = when or _today_local()
    search_count = hit = miss = reuse_ops = 0
    for r in load_records(root):
        if _local_date_of(r.get("ts")) != when:
            continue
        action = r.get("action")
        if action == "search":
            search_count += 1
            if int(r.get("hit_count") or 0) > 0:
                hit += 1
            else:
                miss += 1
        elif action == "reuse":
            reuse_ops += 1

    hit_rate = round(hit / search_count, 4) if search_count else None
    return {
        "date": when.isoformat(),
        "total_cards": _total_cards(root),
        "vector_rows": _vector_rows(root),
        "search_count": search_count,
        "hit": hit,
        "miss": miss,
        "hit_rate": hit_rate,
        "reuse_ops": reuse_ops,
    }


def append(root: Path, row: dict) -> None:
    """append-only 追加一行；目录不存在则创建。幂等由巡检单日一次保证。"""
    d = Path(root) / LOG_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / METRICS.name
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metrics-daily", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument(
        "--date", default=None, help="要聚合的本地日期 YYYY-MM-DD（默认今天）"
    )
    ap.add_argument("--json", action="store_true", help="只输出本次行，不落盘")
    ap.add_argument("--no-append", action="store_true", help="聚合但不写 metrics.jsonl")
    args = ap.parse_args(argv)

    root = Path(args.root)
    when = date.fromisoformat(args.date) if args.date else _today_local()
    row = compute(root, when)

    if args.json or args.no_append:
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return 0

    append(root, row)
    print(
        f"metrics 已追加 {row['date']}: "
        f"cards={row['total_cards']} vectors={row['vector_rows']} "
        f"search={row['search_count']} hit_rate={row['hit_rate']} reuse={row['reuse_ops']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
