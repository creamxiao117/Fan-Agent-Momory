"""高频未命中查询 → 补卡/补 tag 候选清单（建议 2：自我增强闭环）。

消费 `.sync/state/query.log.jsonl`（MCP hub_search 审计），聚合 `action==search` 记录，
按查询文本归一化分组，识别两类知识缺口并给建议动作，输出候选清单交人工审核后走 ingest：

- **P0 · 完全未命中**（hit_count==0）：词袋+向量融合都召回不到任何卡 → 大概率真实知识缺口，
  建议「新增卡片」沉淀该主题规则/经验。
- **P1 · 低命中**（hits>0 但平均 hit_count 小于阈值）：能召回但召回量少/不稳 →
  建议为现有相关卡「增补 tag / 别名」，让确定性通道更稳。

只读分析 + 输出清单，不自动写卡（补卡需人工确认，与 sync ingest 收件箱一致）。
`--since-days N` 限定只分析最近 N 天（A1：每日自动产出的近期缺口候选），默认全历史。

用法：
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub            # Markdown 到终端
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub --json     # 结构化到 stdout
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub -o work/missing.md
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub --since-days 7 -o work/missing.md
"""

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"
LOW_HIT_DEFAULT = 3  # P1 判定：平均命中数低于该值视为低命中
LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai


def load_records(root: Path) -> list[dict]:
    log = Path(root) / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 容忍残行，不影响分析
    return out


def _norm(query: str) -> str:
    return " ".join(query.split()).lower()


def _local_ts_date(ts) -> date | None:
    """query.log `ts` 为 UTC ISO；转本地 +8 取日期。缺失/非法返回 None（当作近期保留）。"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone(LOCAL_TZ).date()
    except ValueError:
        return None


def aggregate(root: Path, since: date | None = None) -> list[dict]:
    """按归一化查询聚合 search 事件 → 按缺口严重度降序的候选列表。

    `since` 非空时只保留该日期（含）之后的记录，用于聚焦近期高频缺口（A1 每日候选）。
    每项: {query, count, misses, hits, zero_ratio, avg_hit, channels, stage}
    stage ∈ {"P0-新增卡片", "P1-补tag别名", "ok-无需处理"}
    """
    grp: dict[str, dict] = {}
    for r in load_records(root):
        if r.get("action") != "search":
            continue
        if since is not None:
            d = _local_ts_date(r.get("ts"))
            if d is not None and d < since:
                continue
        q = r.get("query")
        if not q or not str(q).strip():
            continue
        key = _norm(str(q))
        g = grp.setdefault(
            key,
            {
                "query": str(q).strip(),
                "count": 0,
                "misses": 0,
                "hits": 0,
                "hit_sum": 0,
                "channels": set(),
            },
        )
        g["count"] += 1
        g["channels"].add(r.get("channel", "?"))
        hc = int(r.get("hit_count") or 0)
        g["hit_sum"] += hc
        if hc == 0:
            g["misses"] += 1
        else:
            g["hits"] += 1

    out = []
    for g in grp.values():
        avg_hit = g["hit_sum"] / g["count"]
        zero_ratio = g["misses"] / g["count"]
        if zero_ratio >= 0.5:
            stage = "P0-新增卡片"
        elif avg_hit < LOW_HIT_DEFAULT:
            stage = "P1-补tag别名"
        else:
            stage = "ok-无需处理"
        out.append(
            {
                "query": g["query"],
                "count": g["count"],
                "misses": g["misses"],
                "hits": g["hits"],
                "zero_ratio": round(zero_ratio, 2),
                "avg_hit": round(avg_hit, 2),
                "channels": sorted(g["channels"]),
                "stage": stage,
            }
        )
    # 缺口严重度：先按 stage（P0 < P1 < ok），P0 内按 (zero_ratio, count) 降序
    order = {"P0-新增卡片": 0, "P1-补tag别名": 1, "ok-无需处理": 2}
    out.sort(key=lambda x: (order[x["stage"]], -x["zero_ratio"], -x["count"]))
    return out


def to_markdown(cands: list[dict]) -> str:
    p0 = [c for c in cands if c["stage"].startswith("P0")]
    p1 = [c for c in cands if c["stage"].startswith("P1")]
    lines = [
        "# 高频未命中查询 → 补卡候选清单",
        "",
        f"- P0 完全未命中（建议新增卡片）：{len(p0)} 条",
        f"- P1 低命中（建议补 tag/别名）：{len(p1)} 条",
        "",
    ]
    if p0:
        lines += [
            "## P0 · 完全未命中（知识缺口 → 建议新增卡片）",
            "",
            "| 查询 | 次数 | 零命中占比 | 通道 |",
            "| --- | --- | --- | --- |",
        ]
        for c in p0:
            lines.append(
                f"| {c['query']} | {c['count']} | {c['zero_ratio']:.0%} | {','.join(c['channels'])} |"
            )
        lines.append("")
    if p1:
        lines += [
            "## P1 · 低命中（建议为现有相关卡补 tag/别名）",
            "",
            "| 查询 | 次数 | 平均命中 | 通道 |",
            "| --- | --- | --- | --- |",
        ]
        for c in p1:
            lines.append(
                f"| {c['query']} | {c['count']} | {c['avg_hit']} | {','.join(c['channels'])} |"
            )
        lines.append("")
    if not (p0 or p1):
        lines.append("（无缺口候选）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="missing-query", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON 到 stdout")
    ap.add_argument("-o", "--output", default=None, help="写入 Markdown 文件路径")
    ap.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="只分析最近 N 天（本地日期含当天）；A1 每日候选聚焦近期缺口，默认全历史",
    )
    ap.add_argument(
        "--auto-apply-p1",
        action="store_true",
        default=False,
        help="自动应用低风险 P1 候选补 tag（需满足查询次数≥3，零命中≤30%%等条件）",
    )
    ap.add_argument(
        "--hub-root",
        default="",
        help="中枢根目录（默认与 --root 相同），用于写入 tag",
    )
    ap.add_argument(
        "--auto-draft",
        action="store_true",
        default=False,
        help="自动创建草稿：将高频完全未命中查询生成草稿到 .sync/drafts/",
    )
    ap.add_argument(
        "--min-count",
        type=int,
        default=3,
        help="自动草稿的最小查询次数阈值（默认 3）",
    )
    ap.add_argument(
        "--max-drafts",
        type=int,
        default=5,
        help="每次最多生成的草稿数量（默认 5）",
    )
    args = ap.parse_args(argv)
    root = Path(args.root)
    since = None
    if args.since_days is not None:
        since = datetime.now(LOCAL_TZ).date() - timedelta(days=args.since_days - 1)

    # P0 自动草稿沉淀模式
    if args.auto_draft:
        result = auto_create_drafts(
            root,
            since_days=args.since_days or 7,
            min_count=args.min_count,
            max_drafts=args.max_drafts,
        )
        print("=== P0 自动草稿沉淀结果 ===")
        print(f"P0 候选总数: {result['total_p0_candidates']}")
        print(f"已创建草稿: {result['created_count']}")
        print(f"跳过: {result['skipped_count']}")
        for item in result["created"]:
            print(f"  ✅ {item['query'][:50]}... ({item['count']}次) → {item['file']}")
        for item in result["skipped"]:
            print(f"  ⏭️ {item['query'][:40]}... ({item['reason']})")
        return 0

    # P1 自动补 tag 模式（⚠️ 2026-09-02 冲突合并：auto_apply_p1_tags 函数体在
    # trae work 会话中未随冲突块落盘，全仓查无定义。此处显式占位防 NameError，
    # 保留参数与分支意图，待 trae 侧补齐实现后替换回直接调用。）
    if args.auto_apply_p1:
        raise NotImplementedError(
            "--auto-apply-p1 未实现：auto_apply_p1_tags() 函数体缺失"
            "（trae work 在制品，见 2026-09-02 冲突合并注释）"
        )
    cands = aggregate(root, since=since)
    if args.json:
        print(json.dumps(cands, ensure_ascii=False, indent=2))
        return 0
    md = to_markdown(cands)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"候选清单已写入：{args.output}")
    else:
        print(md)
    return 0


def _tag_suggestion_tokens(query: str) -> list[str]:
    """从查询文本提取候选 tag token（供草稿"关键词提取"节使用）。

    代完成注记（2026-09-02 冲突合并）：原实现未随 trae work 冲突块落盘，
    此处按最小意图补齐——jieba 分词（缺库退化为整串+切分），取去重后的
    2 字以上词，按长度降序（长词信息量高）。
    """
    try:
        import jieba

        words = list(jieba.cut(query))
    except ImportError:
        words = re.split(r"[\s,，。、？！?!:：;；/\\()（）]+", query)
    seen: dict[str, None] = {}
    for w in words:
        w = w.strip().lower()
        if len(w) >= 2 and not seen.get(w):
            seen[w] = None
    return sorted(seen, key=lambda x: (-len(x), x))


def auto_create_drafts(
    root: Path,
    since_days: int = 7,
    min_count: int = 3,
    max_drafts: int = 5,
) -> dict:
    """P0 自动草稿沉淀：将高频完全未命中查询自动生成草稿。

    条件：查询次数 ≥ min_count AND 零命中占比 ≥ 0.5（完全未命中）。
    生成草稿到 .sync/drafts/ 目录，供飞轮 ingest 流程处理。

    返回操作结果。
    """
    since = datetime.now(LOCAL_TZ).date() - timedelta(days=since_days - 1)
    candidates = aggregate(root, since=since)
    p0_items = [c for c in candidates if c["stage"] == "P0-新增卡片" and c["count"] >= min_count]

    drafts_dir = root / ".sync" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    created = []
    skipped = []
    timestamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")

    # 限制批量数量，避免一次性产生过多草稿
    for item in p0_items[:max_drafts]:
        query = item["query"]
        # 生成安全的文件名
        safe_name = re.sub(r"[^\w\u4e00-\u9fff]+", "-", query)[:50].strip("-")
        if not safe_name:
            safe_name = f"query-{hash(query) % 10000:04d}"

        draft_path = drafts_dir / f"{timestamp}-{safe_name}.md"

        # 检查是否已存在相同查询的草稿
        existing_drafts = list(drafts_dir.glob(f"*-{safe_name}.md"))
        if existing_drafts:
            skipped.append({"query": query, "reason": f"已存在 {len(existing_drafts)} 个草稿"})
            continue

        # 生成草稿内容（experience 类型）
        draft_content = f"""---
title: "{query}"
type: experience
status: pending
tags: [查询未命中, 待补充, {query[:10]}]
source: auto-draft
created: {datetime.now(LOCAL_TZ).isoformat()}
query_count: {item['count']}
zero_ratio: {item['zero_ratio']}
---

# 查询未命中：{query}

## 背景
该查询在最近 {since_days} 天内共执行 **{item['count']}** 次，
零命中占比 **{item['zero_ratio']:.0%}**，说明当前知识库可能缺少相关内容。

## 查询详情
- **查询词**: {query}
- **查询次数**: {item['count']}
- **零命中次数**: {item['misses']}
- **平均命中**: {item['avg_hit']}
- **来源平台**: {', '.join(item['channels'])}

## 建议
1. 确认该主题是否应该纳入知识库
2. 如果是，补充相关卡片内容
3. 补充后运行 `build-vectors` 更新向量索引

## 关键词提取
{", ".join(_tag_suggestion_tokens(query)[:5])}
"""

        draft_path.write_text(draft_content, encoding="utf-8")
        created.append({
            "query": query,
            "count": item["count"],
            "file": draft_path.name,
        })

    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
        "total_p0_candidates": len(p0_items),
    }


if __name__ == "__main__":
    raise SystemExit(main())
