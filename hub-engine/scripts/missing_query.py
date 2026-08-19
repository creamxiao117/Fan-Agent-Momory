"""高频未命中查询 → 补卡/补 tag 候选清单（建议 2：自我增强闭环）。

消费 `.sync/state/query.log.jsonl`（MCP hub_search 审计），聚合 `action==search` 记录，
按查询文本归一化分组，识别两类知识缺口并给建议动作，输出候选清单交人工审核后走 ingest：

- **P0 · 完全未命中**（hit_count==0）：词袋+向量融合都召回不到任何卡 → 大概率真实知识缺口，
  建议「新增卡片」沉淀该主题规则/经验。
- **P1 · 低命中**（hits>0 但平均 hit_count 小于阈值）：能召回但召回量少/不稳 →
  建议为现有相关卡「增补 tag / 别名」，让确定性通道更稳。

只读分析 + 输出清单，不自动写卡（补卡需人工确认，与 sync ingest 收件箱一致）。

用法：
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub            # Markdown 到终端
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub --json     # 结构化到 stdout
  python hub-engine/scripts/missing_query.py --root AgentMemoryHub -o work/missing.md
"""

import argparse
import json
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"
LOW_HIT_DEFAULT = 3  # P1 判定：平均命中数低于该值视为低命中


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


def aggregate(root: Path) -> list[dict]:
    """按归一化查询聚合 search 事件 → 按缺口严重度降序的候选列表。

    每项: {query, count, misses, hits, zero_ratio, avg_hit, channels, stage}
    stage ∈ {"P0-新增卡片", "P1-补tag别名", "ok-无需处理"}
    """
    grp: dict[str, dict] = {}
    for r in load_records(root):
        if r.get("action") != "search":
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
    out.sort(
        key=lambda x: (order[x["stage"]], -x["zero_ratio"], -x["count"])
    )
    return out


def to_markdown(cands: list[dict]) -> str:
    p0 = [c for c in cands if c["stage"].startswith("P0")]
    p1 = [c for c in cands if c["stage"].startswith("P1")]
    lines = ["# 高频未命中查询 → 补卡候选清单", ""
             , f"- P0 完全未命中（建议新增卡片）：{len(p0)} 条", f"- P1 低命中（建议补 tag/别名）：{len(p1)} 条", ""]
    if p0:
        lines += ["## P0 · 完全未命中（知识缺口 → 建议新增卡片）", "",
                  "| 查询 | 次数 | 零命中占比 | 通道 |", "| --- | --- | --- | --- |"]
        for c in p0:
            lines.append(
                f"| {c['query']} | {c['count']} | {c['zero_ratio']:.0%} | {','.join(c['channels'])} |"
            )
        lines.append("")
    if p1:
        lines += ["## P1 · 低命中（建议为现有相关卡补 tag/别名）", "",
                  "| 查询 | 次数 | 平均命中 | 通道 |", "| --- | --- | --- | --- |"]
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
    args = ap.parse_args(argv)
    root = Path(args.root)
    cands = aggregate(root)
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


if __name__ == "__main__":
    raise SystemExit(main())