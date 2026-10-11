# @version V1.0 / 2026-10-10 / pi / 涨星第二源：自建每日 star 快照（把「2 周涨星」从 claim 变 measured）
"""star_trend_snapshot —— 自建 GitHub star 快照账本，为「近 2 周涨星」提供**可复算**的第二源。

## 为什么需要它（2026-10-10 用户批准）

star-distill 定时任务的选仓口径是「近 2 周 star 增长最快的前 3 名」，但**没有任何数据源
直接给出 2 周涨星**：

| 源 | 现状 | 结论 |
|---|---|---|
| GitHub Trending `?since=weekly` | 只给**周**涨星（本机实抓可用） | 2 周值只能 ×2 外推 ⇒ `claim` |
| OSS Insight `trends/repos` | 2026-03-01 起事件流只剩 0.3%、返回空 | **不可用** |
| star-history.com | 图形页需抓图/接口非公开稳定 | 不作依赖 |

**唯一可复算的路子 = 自己每天记一次快照，14 天后做差**（本脚本）。
在那之前，调用方仍按 Trending 周值 ×2 退化为 `claim` 并如实标注证据等级（沿用 job 现有口径）。

## 账本格式（append-only JSONL，机器写、人可读）

    {"day": "2026-10-10", "slug": "mvschwarz/openrig", "stars": 6963, "source": "gh-api"}

- 同一 `(day, slug)` 重复记录 **以后写为准**（`record()` 先删同键旧行再追加）——
  JIT 加载/重跑不会污染账本，也不会因重复行把 delta 算歪。
- `source` 记录取数通道（`gh-api` / `trending-page`），便于日后判断可信度。

## 用法

    python -m scripts.star_trend_snapshot record-trending --limit 25   # 每日一次（攒历史）
    python -m scripts.star_trend_snapshot record --slug owner/repo [--slug ...]
    python -m scripts.star_trend_snapshot query --slug owner/repo --days 14 [--json]
    python -m scripts.star_trend_snapshot show --limit 10

退出码：0 正常｜2 `query` 拿不到足够历史（调用方据此退化为 claim，**不是错误**）。

## 口径与边界

- `delta()` 只在**账本内最早一条记录已 ≥ days 天**时返回 `measured`；否则
  `measured-partial`（给出实际跨度与涨星数，供人判断是否够用），无记录则 `None`。
- 不做任何「按周值 ×2」的推算——那是调用方（job prompt）的退化路径，且必须标 `claim`。
- 本脚本只读 GitHub 公开数据（`gh api` / Trending 页面），不登录、不写远端。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

LEDGER_REL = Path("system") / "run" / "star-trend.jsonl"
TRENDING_URL = "https://github.com/trending?since=weekly"
DEFAULT_DAYS = 14

# Trending 页面里的仓库链接：<a href="/owner/repo" ...>（owner/repo 均为 GitHub 合法字符集）
_TRENDING_RE = re.compile(r'href="/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"')
# 非仓库路径（Trending 页面的导航/分类链接），显式排除，避免把 "trending/daily" 当仓库
_NOT_REPO = {"trending", "topics", "collections", "sponsors", "marketplace", "login", "signup"}


def today_iso(day: str | None = None) -> str:
    return day or date.today().isoformat()


def read_ledger(path: Path) -> list[dict]:
    """读账本；坏行**跳过不报错**（一行坏数据不该让整本不可用）。"""
    if not Path(path).is_file():
        return []
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("slug") and rec.get("day"):
            out.append(rec)
    return out


def record(path: Path, slug: str, stars: int, day: str | None = None, source: str = "gh-api") -> bool:
    """记一条快照；同 `(day, slug)` 覆盖旧值。返回是否真的写入了新内容（幂等：同值返回 False）。"""
    path = Path(path)
    day = today_iso(day)
    existing = read_ledger(path)
    same_key = [r for r in existing if r.get("day") == day and r.get("slug") == slug]
    if len(same_key) == 1 and int(same_key[0].get("stars", -1)) == int(stars):
        return False  # 完全一致：不重写，避免 mtime 抖动
    kept = [r for r in existing if not (r.get("day") == day and r.get("slug") == slug)]
    kept.append({"day": day, "slug": slug, "stars": int(stars), "source": source})
    kept.sort(key=lambda r: (str(r["day"]), str(r["slug"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def delta(records: list[dict], slug: str, *, days: int = DEFAULT_DAYS, today: str | None = None) -> dict | None:
    """`slug` 在最近 `days` 天窗口内的涨星。

    返回 `{"slug","stars_now","stars_then","delta","span_days","evidence","day_now","day_then"}`
    或 `None`（无记录）。

    `evidence`：
      - `measured`          —— 账本内存在 ≥ days 天前的记录（口径达标，可当实测用）
      - `measured-partial`  —— 只有窗口内的记录（跨度不足；数字是真实的，但**不是 2 周口径**）
    """
    today = today_iso(today)
    t_today = datetime.fromisoformat(today).date()
    mine = [r for r in records if r.get("slug") == slug]
    if not mine:
        return None
    mine.sort(key=lambda r: str(r["day"]))
    # 「今天」取不晚于 today 的最新一条；「窗口起点」取 ≤ today-days 的最近一条（没有则取最早一条）
    floor = t_today - timedelta(days=days)
    at_or_before_today = [r for r in mine if datetime.fromisoformat(str(r["day"])).date() <= t_today]
    if not at_or_before_today:
        return None
    now = at_or_before_today[-1]
    older = [r for r in at_or_before_today if datetime.fromisoformat(str(r["day"])).date() <= floor]
    then = older[-1] if older else at_or_before_today[0]
    if then.get("day") == now.get("day"):
        return None  # 只有一天的数据：涨星无从谈起
    span = (datetime.fromisoformat(str(now["day"])).date() - datetime.fromisoformat(str(then["day"])).date()).days
    return {
        "slug": slug,
        "stars_now": int(now["stars"]),
        "stars_then": int(then["stars"]),
        "delta": int(now["stars"]) - int(then["stars"]),
        "span_days": span,
        "evidence": "measured" if older else "measured-partial",
        "day_now": str(now["day"]),
        "day_then": str(then["day"]),
    }


def parse_trending(html: str) -> list[str]:
    """从 Trending 页面 HTML 抽 `owner/repo`（保持页面顺序，去重）。"""
    out: list[str] = []
    for owner, repo in _TRENDING_RE.findall(html or ""):
        if owner.lower() in _NOT_REPO or repo.lower() in _NOT_REPO:
            continue
        slug = f"{owner}/{repo}"
        if slug not in out:
            out.append(slug)
    return out


def fetch_trending(limit: int | None = None) -> list[str]:
    """抓 Trending weekly 页面 → slug 列表（需要网络）。"""
    import requests

    resp = requests.get(TRENDING_URL, timeout=30, headers={"User-Agent": "agent-memory-hub/1.0"})
    resp.raise_for_status()
    slugs = parse_trending(resp.text)
    return slugs[:limit] if limit else slugs


def fetch_stars(slug: str, *, timeout: int = 30) -> int | None:
    """`gh api repos/<slug> --jq .stargazers_count`（用既有 gh 登录态，不新建登录）。"""
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{slug}", "--jq", ".stargazers_count"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return int(str(r.stdout).strip())
    except ValueError:
        return None


def _cmd_record(args) -> int:
    ledger = Path(args.hub) / LEDGER_REL
    wrote = 0
    for slug in args.slug or []:
        stars = fetch_stars(slug)
        if stars is None:
            print(f"[star-trend] 取数失败，跳过: {slug}", file=sys.stderr)
            continue
        if record(ledger, slug, stars, source="gh-api"):
            wrote += 1
        print(f"[star-trend] {slug} = {stars}★")
    print(f"[star-trend] 写入 {wrote} 条 → {ledger}")
    return 0


def _cmd_record_trending(args) -> int:
    ledger = Path(args.hub) / LEDGER_REL
    slugs = fetch_trending(limit=args.limit)
    if not slugs:
        print("[star-trend] Trending 未解析到任何仓库（页面结构可能变了）", file=sys.stderr)
        return 2
    wrote = 0
    for slug in slugs:
        stars = fetch_stars(slug)
        if stars is None:
            continue
        if record(ledger, slug, stars, source="gh-api"):
            wrote += 1
    print(f"[star-trend] Trending {len(slugs)} 仓 → 新写入 {wrote} 条 → {ledger}")
    return 0


def _cmd_query(args) -> int:
    ledger = Path(args.hub) / LEDGER_REL
    d = delta(read_ledger(ledger), args.slug, days=args.days)
    if d is None:
        if args.json:
            print(
                json.dumps(
                    {
                        "slug": args.slug,
                        "evidence": "none",
                        "hint": "无快照历史 → 调用方退化为 Trending 周值×2（claim）",
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[star-trend] {args.slug}: 无足够历史 → 退化口径（Trending 周值×2，标注 claim）")
        return 2
    if args.json:
        print(json.dumps(d, ensure_ascii=False))
    else:
        print(
            f"[star-trend] {args.slug}: {d['delta']:+d}★ / {d['span_days']} 天"
            f"（{d['stars_then']} → {d['stars_now']}，{d['day_then']} → {d['day_now']}，证据={d['evidence']}）"
        )
    return 0 if d["evidence"] == "measured" else 2


def _cmd_show(args) -> int:
    ledger = Path(args.hub) / LEDGER_REL
    recs = read_ledger(ledger)
    days = sorted({r["day"] for r in recs})
    print(f"[star-trend] 账本 {ledger}")
    print(f"[star-trend] 记录 {len(recs)} 条 · 覆盖 {len(days)} 天 · slug {len({r['slug'] for r in recs})} 个")
    for day in days[-args.limit :]:
        print(f"  {day}: {sum(1 for r in recs if r['day'] == day)} 条")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="自建 GitHub star 快照账本（涨星第二源）")
    ap.add_argument("--hub", default=str(_HUB_ENGINE.parent / "AgentMemoryHub"), help="中枢根目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="记录指定仓库的当前 star 数")
    p.add_argument("--slug", action="append", required=True, help="owner/repo（可重复）")
    p.set_defaults(func=_cmd_record)

    p = sub.add_parser("record-trending", help="抓 Trending weekly 并记录其中每个仓库的 star 数")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=_cmd_record_trending)

    p = sub.add_parser("query", help="查某仓的窗口涨星（exit 2 = 历史不足，退化为 claim）")
    p.add_argument("--slug", required=True)
    p.add_argument("--days", type=int, default=DEFAULT_DAYS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_query)

    p = sub.add_parser("show", help="账本概览")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=_cmd_show)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
