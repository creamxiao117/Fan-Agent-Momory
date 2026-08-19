"""E3 真实召回回归门禁（飞轮 E 环·可验证信号）：把高频未命中查询固化 canary，每日回归检索。

背景：E1 已把中枢成长度量落成 `metrics.jsonl`；E3 补「检索管线还活着吗」的回归门禁——
从 `query.log` 抽 **高频 + 完全未命中（P0）** 查询，固化成快照 `.sync/state/real_regression.json`
（跨日稳定，即「固定集」），每日对它们跑语义等价检索，**全未命中即 fail**（默认 gate）；
`--fail-below X` 可抬阈值，拦掉部分退化。命中即召回 >=1 张卡（canary 检出整条检索
词袋+向量融合管线崩溃 / 模型不可用导致的整库零召回）。

设计要点：
- 命中判定与 `hub_search` 一致：`tools.retrieve.retrieve_with_meta` 返回的 scored 数 >0 即命中；
  本门禁**不写审计**，只读，不污染 `query.log`。
- 固定集快照：跨日稳定，仅 `--refresh` 或超过 `--max-age-days`（默认 7 天）时才从 query.log 重建。
- 无可用 P0 未命中断言样本（健康中枢）→ 跳过门禁、返回 0，不误报警。

退出码契约（沿用 `patrol-alert-exit-code`）：0=通过（含无样本正常跳过）；3=回归门禁未过。

用法：
  python hub-engine/scripts/real_query_regression.py --root AgentMemoryHub             # 每日：固定集跑门禁
  python hub-engine/scripts/real_query_regression.py --root AgentMemoryHub --refresh   # 重建 canary 集
  python hub-engine/scripts/real_query_regression.py --root AgentMemoryHub --fail-below 0.5  # 抬阈值
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(
    0, str(_HERE.parents[1])
)  # hub-engine 加入 path，保证单独运行可导入 tools

from tools.retrieve import (
    retrieve_with_meta,
)

LOG = Path(".sync") / "state" / "query.log.jsonl"
SNAPSHOT = Path(".sync") / "state" / "real_regression.json"
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai
# P0 判定与 missing_query 一致：完全未命中占比 >= 0.5 视为知识缺口
ZERO_RATIO_P0 = 0.5


def _today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def _norm(query: str) -> str:
    return " ".join(query.split()).lower()


def load_records(root: Path) -> list[dict]:
    """读取 query.log.jsonl，容忍残行，不存在返回空。"""
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


def candidates(root: Path, min_count: int) -> list[dict]:
    """从 query.log 抽「高频 + 完全未命中(P0)」查询，作 canary 集候选，按缺口严重度降序。

    返回 [{query, count}]：归一化聚合，count>=min_count 且零命中占比 >=0.5。
    """
    grp: dict[str, dict] = {}
    for r in load_records(root):
        if r.get("action") != "search":
            continue
        q = str(r.get("query") or "").strip()
        if not q:
            continue
        key = _norm(q)
        g = grp.setdefault(key, {"query": q, "count": 0, "misses": 0})
        g["count"] += 1
        if int(r.get("hit_count") or 0) == 0:
            g["misses"] += 1

    out = []
    for g in grp.values():
        if g["count"] < min_count:
            continue
        if g["misses"] / g["count"] < ZERO_RATIO_P0:
            continue
        out.append({"query": g["query"], "count": g["count"]})
    out.sort(key=lambda x: (-x["count"], x["query"]))
    return out


def snapshot_path(root: Path) -> Path:
    return Path(root) / SNAPSHOT


def persist_snapshot(
    root: Path, items: list[dict], refreshed: str | None = None
) -> None:
    d = Path(root) / SNAPSHOT.parent
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "refreshed": refreshed or _today_local().isoformat(),
        "queries": items,
    }
    payload_path = d / SNAPSHOT.name
    payload_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_snapshot(root: Path) -> list[dict] | None:
    """读固定集快照；缺失或损坏返回 None（调用方据此触发重建）。"""
    p = snapshot_path(root)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return None
    return [
        {"query": str(it.get("query") or ""), "count": int(it.get("count") or 0)}
        for it in queries
        if it
    ]


def snapshot_age_days(root: Path, today: date | None = None) -> int | None:
    """固定集快照的「刷新距今」天数；无快照返回 None。"""
    p = snapshot_path(root)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        ref = date.fromisoformat(str(payload.get("refreshed")))
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    return ((today or _today_local()) - ref).days


def ensure_set(
    root: Path,
    min_count: int,
    max_age_days: int,
    force_refresh: bool,
    today: date | None = None,
) -> tuple[list[dict], bool]:
    """返回 (固定集 items, 是否本次从 query.log 重建)。

    决策：force_refresh 或快照缺失/超龄 → 重建并落盘；否则读缓存（跨日稳定）。
    """
    today = today or _today_local()
    age = snapshot_age_days(root, today)
    from_log = force_refresh or age is None or age >= max_age_days
    if from_log:
        items = candidates(root, min_count)
        persist_snapshot(root, items, today.isoformat())
        return items, True
    cached = load_snapshot(root)
    return (cached or [], False)


def gate_stats(items: list[dict], hit_fn) -> dict:
    """对固定集逐查询跑 hit_fn(q)->bool，聚合成门禁统计。

    返回 {total, hits, hit_ratio, miss_queries}。
    """
    miss = []
    hits = 0
    for it in items:
        q = it["query"]
        if hit_fn(q):
            hits += 1
        else:
            miss.append(q)
    total = len(items)
    ratio = round(hits / total, 4) if total else None
    return {"total": total, "hits": hits, "hit_ratio": ratio, "miss_queries": miss}


def gate_failed(hit_ratio: float | None, fail_below: float | None) -> bool:
    """门禁判定：默认全未命中即 fail（ratio==0）；给定 --fail-below 则低于阈值即 fail。"""
    if hit_ratio is None:
        return True  # 防御：空集本不该走到判定
    if fail_below is None:
        return hit_ratio == 0.0
    return hit_ratio < fail_below


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="real-query-regression", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument(
        "--model", default=DEFAULT_MODEL, help="HF 向量模型 id（与建库一致）"
    )
    ap.add_argument("--min-count", type=int, default=2, help="作为 canary 的最低频次")
    ap.add_argument(
        "--max-age-days", type=int, default=7, help="固定集超龄天数触发重建"
    )
    ap.add_argument("--top-k", type=int, default=5, help="检索 top_k")
    ap.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="命中率低于该值判失败（默认全未命中才判失败）",
    )
    ap.add_argument(
        "--refresh", action="store_true", help="强制从 query.log 重建固定集"
    )
    args = ap.parse_args(argv)

    root = Path(args.root)
    os.environ["AGENT_MD_EMBED_MODEL"] = args.model  # 检索读现向量库，模型须与建库一致

    items, from_log = ensure_set(
        root,
        args.min_count,
        args.max_age_days,
        args.refresh,
    )
    if not items:
        print(
            "检索回归门禁：无「高频未命中」断言样本（检索健康），跳过（无法断言待补卡缺口）。"
        )
        return 0

    def hit_fn(q: str) -> bool:
        _, scored = retrieve_with_meta(root, q, top_k=args.top_k)
        return bool(scored)

    stats = gate_stats(items, hit_fn)
    ratio = stats["hit_ratio"]
    source = "（本次从 query.log 重建）" if from_log else "（读取固定集缓存）"
    print(
        f"检索回归 canary {source}: 命中 {stats['hits']}/{stats['total']} = {ratio:.0%}"
    )
    if stats["miss_queries"]:
        print("  未命中断言样本: " + ", ".join(stats["miss_queries"]))

    if gate_failed(ratio, args.fail_below):
        reason = (
            "全未命中"
            if args.fail_below is None
            else f"命中率 {ratio:.0%} < 阈值 {args.fail_below:.0%}"
        )
        print(f"【告警】检索回归门禁未过：{reason}——词袋+向量融合管线疑似退化。")
        return 3  # 专用退出码：回归门禁未通过
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
