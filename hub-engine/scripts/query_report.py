"""台账周报：MCP 查询调用 + **去重链判决**（两个台账都在 `.sync/state/`）。

两个台账
--------
| 台账 | 文件 | 记什么 |
| -- | -- | -- |
| 查询账本 | `.sync/state/query.log*.jsonl` | 各平台的检索/引导调用（MCP 与 tier-bootstrap 都写） |
| **去重判决台账** | `.sync/state/dedup_stats.jsonl` | 每次去重判决的 action / confidence / **是否退化** |

「退化」= 模型输出坏掉（缺字段 / 非法动作 / 解析失败）⇒ 被静默降级成 review。
2026-10-06~10-12 真实发生过：本地模型普遍漏写 `confidence` ⇒ 51 张草稿全判 review 进冲突区
⇒ 产出率塌到 21%/17%，而当时**没有任何面板能看出是退化**（指标还把 review 混进「重复」里）。
⇒ 现在判决台账落盘 + 本脚本汇总 + 巡检第 4 步子检查 ⇒ **退化当天可见**。
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"
DEDUP_LOG = Path(".sync") / "state" / "dedup_stats.jsonl"
CST = timezone(timedelta(hours=8))
DEFAULT_DAYS = 7
# 退化占比阈值：超过它 ⇒ 「去重链输出正在退化」（review 被大量判成坏输出）
DEGRADED_RATIO = 0.2


def load_records(root: Path) -> list[dict]:
    log = Path(root) / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def report(root: Path) -> dict:
    by_platform: dict[str, Counter] = defaultdict(Counter)
    recs = load_records(root)
    for r in recs:
        by_platform[r.get("platform", "unknown")][r.get("action", "?")] += 1
    return {
        "total": len(recs),
        "platforms": {p: dict(c) for p, c in sorted(by_platform.items())},
    }


def _load_dedup_rows(root: Path) -> list[dict]:
    p = Path(root) / DEDUP_LOG
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def dedup_summary(root: Path, days: int = DEFAULT_DAYS) -> dict:
    """去重链判决分布 + **退化**计数（退化占比 ≥20% ⇒ 告警）。"""
    cutoff = datetime.now(CST) - timedelta(days=days)
    rows = []
    for d in _load_dedup_rows(root):
        ts = str(d.get("ts") or "")
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=CST)
        if when >= cutoff:
            rows.append(d)
    actions = Counter(str(r.get("action") or "?") for r in rows)
    degraded = [r for r in rows if r.get("degraded")]
    reasons = Counter(str(r.get("degraded_reason") or "?") for r in degraded)
    ratio = (len(degraded) / len(rows)) if rows else 0.0
    return {
        "window_days": days,
        "total": len(rows),
        "actions": dict(sorted(actions.items())),
        "degraded": len(degraded),
        "degraded_ratio": ratio,
        "degraded_reasons": dict(reasons.most_common(5)),
        "degraded_threshold": DEGRADED_RATIO,
        "degraded_alert": bool(rows) and ratio >= DEGRADED_RATIO,
        "recent_degraded": [
            {
                "ts": r.get("ts"),
                "platform": r.get("platform"),
                "slug": r.get("slug"),
                "reason": r.get("degraded_reason"),
            }
            for r in degraded[-5:]
        ],
    }


def render_dedup(s: dict) -> str:
    lines = [f"# 去重链健康（近 {s['window_days']} 天）", ""]
    if not s["total"]:
        lines.append("- 判决台账为空（尚无记录，或 ingest 尚未命中重复候选）")
        return "\n".join(lines)
    lines.append(f"- 判决总数 **{s['total']}**")
    lines.append("- 判决分布：" + " · ".join(f"{k}={v}" for k, v in s["actions"].items()))
    lines.append(
        f"- **退化（模型输出坏掉⇒静默降级 review）**：{s['degraded']} 条"
        f"（占比 {s['degraded_ratio']:.0%}，阈值 {s['degraded_threshold']:.0%}）"
        + ("　⚠️ **去重链正在退化**" if s["degraded_alert"] else "　✅ 正常")
    )
    if s["degraded_reasons"]:
        lines.append("- 退化原因：" + "、".join(f"{k}×{v}" for k, v in s["degraded_reasons"].items()))
    if s["recent_degraded"]:
        lines.append("- 最近退化样例：")
        for r in s["recent_degraded"]:
            lines.append(f"  - {r.get('ts')} {r.get('platform')}/{r.get('slug')}：{r.get('reason')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="query-report")
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--dedup", action="store_true", help="改看**去重链判决**台账（分布 + 退化）")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="去重台账统计窗（天）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.dedup:
        s = dedup_summary(root, args.days)
        print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else render_dedup(s))
        return 2 if s["degraded_alert"] else 0
    print(json.dumps(report(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
