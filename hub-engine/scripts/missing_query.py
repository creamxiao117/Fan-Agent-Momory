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
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# 脚本直跑引导：把 hub-engine 根加入 sys.path（与 session_preload 同惯例；
# pytest 经 pyproject pythonpath 注入故单测不受影响）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def auto_apply_p1_tags(root: Path, hub_root: Path) -> dict:
    """P1 自动补 tag：将低命中高频查询的关键词追加到最相关卡的 frontmatter tags。

    执行端设计（2026-09-02 Hermes 补全，契约按调用点还原）：
    - 候选：aggregate(root) 中 stage==P1-补tag别名，且 count>=P1_MIN_COUNT、
      zero_ratio<=P1_MAX_ZERO_RATIO（对应 CLI help 的"查询次数≥3，零命中≤30%"）。
    - 提词：_tag_suggestion_tokens(query) 取前 5。
    - 目标卡：retrieve_with_meta(hub_root, query, top_k=2) 的前 2 张权威区卡
      （只追加 tag，不改正文/status/其他字段；write_card 保 extra 无损）。
    - 安全：全程持 _WriteLock（单写者锁，与 ingest 互斥）；validate_card 非空
      错误列表的卡拒写；幂等（已含该 tag 跳过）；改后 git 精确提交回滚点。
    - 审计：memory_diff 记录 + retro/log.md append-only。
    - rule/methodology（HIGH_RISK）卡只补 tag 不改语义，与"新规则需人工确认"
      不冲突；但为保守起见本函数只写 tag 字段，永不触碰 status/reuse_count。
    """
    from common.frontmatter import (
        read_card,
        today_iso,
        validate_card,
        write_card,
    )
    from sync import GIT_ID, _append_log, _git, _WriteLock
    from tools.memory_diff import record as record_diff
    from tools.retrieve import retrieve_with_meta

    hub_root = Path(hub_root)
    P1_MIN_COUNT = 3
    P1_MAX_ZERO_RATIO = 0.30
    MAX_TOKENS_PER_QUERY = 5
    TARGET_CARDS = 2

    cands = aggregate(root)
    p1_items = [
        c
        for c in cands
        if c["stage"].startswith("P1")
        and c["count"] >= P1_MIN_COUNT
        and c["zero_ratio"] <= P1_MAX_ZERO_RATIO
    ]

    applied: list[dict] = []
    skipped: list[dict] = []
    dirty: set[str] = set()  # 已改动卡的相对路径（git 精确提交用）

    try:
        lock_ctx = _WriteLock(hub_root)
        lock_ctx.__enter__()
    except RuntimeError as e:
        return {
            "applied_count": 0,
            "skipped_count": len(p1_items),
            "applied": [],
            "skipped": [{"query": c["query"], "reason": str(e)} for c in p1_items],
            "status": str(e),
        }
    try:
        for item in p1_items:
            query = item["query"]
            tokens = _tag_suggestion_tokens(query)[:MAX_TOKENS_PER_QUERY]
            if not tokens:
                skipped.append({"query": query, "reason": "无有效关键词"})
                continue
            _, scored = retrieve_with_meta(hub_root, query, top_k=TARGET_CARDS)
            targets = [c for c, _s in scored[:TARGET_CARDS] if c.path]
            if not targets:
                skipped.append({"query": query, "reason": "无可写入的目标卡"})
                continue
            added_total: list[str] = []
            for card in targets:
                try:
                    fresh = read_card(card.path)
                except (OSError, ValueError):
                    skipped.append(
                        {"query": query, "reason": f"目标卡读取失败 {card.path.name}"}
                    )
                    continue
                have = {t.lower() for t in fresh.tags}
                new_tags = [t for t in tokens if t.lower() not in have]
                if not new_tags:
                    continue  # 幂等：全部已含
                fresh.tags = fresh.tags + new_tags
                fresh.updated = today_iso()
                errs = validate_card(fresh)
                if errs:
                    skipped.append(
                        {
                            "query": query,
                            "reason": f"改后校验失败 {card.path.name}: {errs[0]}",
                        }
                    )
                    continue
                card.path.write_text(write_card(fresh), encoding="utf-8")
                rel = card.path.relative_to(hub_root).as_posix()
                dirty.add(rel)
                added_total.extend(new_tags)
                record_diff(
                    hub_root,
                    {
                        "op": "update",
                        "name": card.path.name,
                        "type": fresh.type,
                        "before": f"tags={sorted(have)}",
                        "after": f"tags={sorted(t.lower() for t in fresh.tags)}",
                        "deleted_content": None,
                    },
                )
            if added_total:
                applied.append(
                    {
                        "query": query,
                        "count": item["count"],
                        "tags_added": sorted(set(added_total)),
                        "cards": len(targets),
                    }
                )
            else:
                skipped.append({"query": query, "reason": "目标卡已含全部候选 tag"})

        if dirty:
            _git(hub_root, "add", *sorted(dirty))
            _git(
                hub_root,
                *GIT_ID,
                "commit",
                "-m",
                f"chore(p1-autotag): 自动补 tag {len(dirty)} 张卡（missing_query P1 执行端，可由本提交回滚）",
            )
            _append_log(
                hub_root,
                "p1-autotag",
                f"补 tag 应用 {len(applied)} 条查询 → {len(dirty)} 张卡",
            )
    finally:
        lock_ctx.__exit__(None, None, None)

    return {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "status": "ok",
    }


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

    # P1 自动补 tag 模式（2026-09-02 Hermes 补全 auto_apply_p1_tags 实现，
    # 行为契约按调用点消费端还原：返回 applied_count/skipped_count/applied[]，
    # 每项含 query 与 tags_added；目标卡写 frontmatter tags 并 git 提交回滚点）
    if args.auto_apply_p1:
        hub_root = Path(args.hub_root) if args.hub_root else root
        result = auto_apply_p1_tags(root, hub_root)
        print("=== P1 自动补 tag 结果 ===")
        print(f"已自动应用: {result['applied_count']} 条")
        print(f"跳过: {result['skipped_count']} 条")
        for item in result["applied"]:
            print(f"  ✅ {item['query'][:60]}... → {len(item['tags_added'])} 张卡加了 tag")
        for item in result["skipped"]:
            print(f"  ⏭️ {item['query'][:40]}... ({item['reason']})")
        # 同时输出候选清单供人工复核
        cands = aggregate(root, since=since)
        md = to_markdown(cands)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(md, encoding="utf-8")
        return 0
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
