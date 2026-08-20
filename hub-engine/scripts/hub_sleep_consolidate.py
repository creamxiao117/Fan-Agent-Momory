"""中枢原生夜间离线自进化引擎 · 收割→挖掘→有界候选→held-out验证→暂存人工采纳（零外发）。

对统一记忆中枢应用 SkillOpt-Sleep 的收敛纪律，但**零外发、零自动改卡**：

- **收割 harvest**：读 query.log（经 `missing_query.aggregate` 内部复用 `load_records`）。
- **挖掘 mine**：聚合出 P0（完全未命中→新增卡）/ P1（低命中→补tag）缺口候选
  （复用 `missing_query.aggregate`）。
- **有界候选 bounded**：`--max-candidates` 限制每晚只暴露少量候选（类比编辑预算/文本学习率）。
- **held-out 验证**：对每个候选跑现检索（复用 `retrieve_with_meta`），标注当前命中状态供人工
  判断；阶段1只报告不自动 accept/reject（人工门禁）。
- **暂存 stage**：写入 `.sync/state/sleep/<日期>/proposal.{md,json}`（git-ignored），绝不写权威区。
- **人工采纳 adopt**：打印暂存路径与 ingest 指引，由人工审核后走 ingest 补卡。

本脚本不调用任何 LLM / 外网，仅本地词袋 + 向量检索，可安全接入每日巡检（零花费、零外发）。

用法：
  python hub-engine/scripts/hub_sleep_consolidate.py --root AgentMemoryHub             # 近7天缺口→暂存候选
  python hub-engine/scripts/hub_sleep_consolidate.py --root AgentMemoryHub --since-days 2
  python hub-engine/scripts/hub_sleep_consolidate.py --root AgentMemoryHub --json      # 结构到 stdout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # hub-engine 加入 path，保证单独运行可导入

from scripts.missing_query import aggregate
from tools.retrieve import retrieve_with_meta

LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
SLEEP_ROOT = Path(".sync") / "state" / "sleep"
_STAGE_RANK = {"P0-新增卡片": 0, "P1-补tag别名": 1, "ok-无需处理": 2}


def _today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def _since_from_days(since_days: int) -> date:
    return _today_local() - timedelta(days=since_days - 1)


def harvest_candidates(
    root: Path, since: date | None, max_candidates: int
) -> list[dict]:
    """收割+挖掘：从 query.log 聚合缺口候选，排序后截取前 max_candidates（有界）。

    返回面试项结构同 missing_query.aggregate 的输出（含 stage），仅保留知识缺口
    （P0 新增卡 / P1 补tag），并按缺口严重度降序、截断到 `max_candidates`。
    """
    cands = [c for c in aggregate(root, since=since) if c["stage"] != "ok-无需处理"]
    cands.sort(
        key=lambda c: (_STAGE_RANK.get(c["stage"], 9), -c["zero_ratio"], -c["count"])
    )
    return cands[:max_candidates]


def enrich_current_hits(cands: list[dict], root: Path, top_k: int) -> list[dict]:
    """held-out 验证：对每个候选跑现检索，标注"当前检索命中张数"（只读，不写审计）。

    让候选带"现在到底命中几张"的观测，供人工判断是否真缺口；P0 但当前能命中多张 = 需更具体。

    （路径A：Continual Harness 的 RefinementEvent 契约）同时补 `evidence` 与 `outcome` 两个只增字段：
    - `evidence`：把散在 count/zero_ratio/avg_hit/stage/current_hits 的证据聚合成可读串，
      让每条候选"为什么进来"可被人为审计，而非只看动作清单。
    - `outcome`：默认 `"待定"`，供人工采纳后回写（adopted/rejected），让"改完是否生效"可回溯。
    """
    out = []
    for c in cands:
        channel, scored = retrieve_with_meta(root, c["query"], top_k=top_k)
        current_hits = len(scored)
        evidence = (
            f"{c['stage']}: 近窗口被查 {c['count']} 次, "
            f"零命中占比 {c['zero_ratio']:.0%}, 平均命中 {c['avg_hit']}; "
            f"现检索命中 {current_hits} 张(通道 {channel})"
        )
        out.append(
            {
                **c,
                "current_channel": channel,
                "current_hits": current_hits,
                "evidence": evidence,
                "outcome": "待定",
            }
        )
    return out


def _draft_card(c: dict) -> str:
    """为 P0 候选生成"待人工补全"的卡草稿骨架（非实测内容，仅供 review 后走 ingest）。"""
    today = _today_local().isoformat()
    return (
        "```yaml\n"
        "---\n"
        "type: note            # 按内容改为 rule/exp/methodology/note 等\n"
        "tags: [待填]          # 从查询主题提炼 tag\n"
        "status: reference\n"
        f"updated: {today}\n"
        "---\n"
        "# <标题>\n\n"
        "## 描述\n"
        f"来自高频未命中查询：`{c['query']}`\n\n"
        "## 正文\n"
        "（人工补全：该主题的规则 / 经验…… 不要照抄查询语句）\n"
        "```"
    )


def _render_markdown(cands: list[dict], meta: dict) -> str:
    today = meta["date"]
    p0 = [c for c in cands if c["stage"].startswith("P0")]
    p1 = [c for c in cands if c["stage"].startswith("P1")]
    lines = [
        f"# 中枢夜间自进化 · {today} 候选（收割→挖掘→暂存，零外发）",
        "",
        f"- P0 完全未命中（建议新增卡片）：{len(p0)} 条",
        f"- P1 低命中（建议补 tag/别名）：{len(p1)} 条",
        "",
        "_本提案仅暂存，未写入权威区。请人工审核后走 `ingest` 落地；无关/误报候选直接忽略。_",
        "",
    ]
    for i, c in enumerate(p0, start=1):
        lines += [
            f"## 候选 {i} · `{c['query']}`",
            "",
            f"- 次数 ×{c['count']} · 零命中占比 {c['zero_ratio']:.0%} → **新增卡片**",
            (
                f"- 当前检索命中：{c.get('current_hits', '—')} 张"
                f"（通道 {c.get('current_channel', '—')}）"
            ),
            f"- 证据：{c.get('evidence', '—')}",
            f"- 结果(outcome)：{c.get('outcome', '待定')}",
            "- 卡草稿：",
            _draft_card(c),
            "",
        ]
    for i, c in enumerate(p1, start=1):
        lines += [
            f"## 候选 {i} · `{c['query']}`",
            "",
            f"- 次数 ×{c['count']} · 平均命中 {c['avg_hit']} → **补 tag/别名**",
            (
                f"- 当前检索命中：{c.get('current_hits', '—')} 张"
                f"（通道 {c.get('current_channel', '—')}）"
            ),
            f"- 证据：{c.get('evidence', '—')}",
            f"- 结果(outcome)：{c.get('outcome', '待定')}",
            "",
        ]
    if not cands:
        lines.append("（本窗口无知识缺口候选）")
        lines.append("")
    lines.append("_采纳路径：把 P0 的卡草稿补全为真实正文 → `engine.py ingest`。_")
    return "\n".join(lines)


def _staging_dir(root: Path, ts: str) -> Path:
    return Path(root) / SLEEP_ROOT / ts


def stage_proposal(root: Path, cands: list[dict]) -> str:
    """把候选提案写入 .sync/state/sleep/<ts>/（git-ignored），返回暂存目录字符串。

    原子写 proposal.md + proposal.json，绝不触碰权威区（对齐 SkillOpt stage 契约）。
    """
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    out = _staging_dir(root, ts)
    out.mkdir(parents=True, exist_ok=True)
    today = _today_local().isoformat()
    meta = {
        "date": today,
        "generated_at": ts,
        "harvest_window_days": None,
        "n_candidates": len(cands),
    }

    (out / "proposal.md").write_text(_render_markdown(cands, meta), encoding="utf-8")
    (out / "proposal.json").write_text(
        json.dumps(
            {"meta": meta, "candidates": cands},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub-sleep-consolidate", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument(
        "--since-days", type=int, default=7, help="收割近 N 天 query.log 缺口（默认 7）"
    )
    ap.add_argument(
        "--max-candidates",
        type=int,
        default=5,
        help="每晚最大候选数（编辑预算/有界，默认 5）",
    )
    ap.add_argument("--top-k", type=int, default=5, help="当前命中验证的检索 top_k")
    ap.add_argument(
        "--model", default=DEFAULT_MODEL, help="HF 向量模型 id（与建库一致）"
    )
    ap.add_argument("--json", action="store_true", help="结构到 stdout（不落盘）")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"中枢根目录不存在：{root}", file=sys.stderr)
        return 2
    os.environ["AGENT_MD_EMBED_MODEL"] = args.model

    today = _today_local()
    since = today - timedelta(days=args.since_days - 1)
    cands = harvest_candidates(root, since, args.max_candidates)
    cands = enrich_current_hits(cands, root, args.top_k)

    if args.json:
        print(
            json.dumps(
                {
                    "date": today.isoformat(),
                    "since": since.isoformat(),
                    "n_candidates": len(cands),
                    "candidates": cands,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    staging = stage_proposal(root, cands)
    p0 = sum(1 for c in cands if c["stage"].startswith("P0"))
    p1 = len(cands) - p0
    print(
        f"[sleep] night harvesting query.log ({args.since_days}天): "
        f"P0 {p0} / P1 {p1} 候选"
    )
    print(f"[sleep] staged: {staging}  (review → ingest 采纳，本脚本未改任何卡)")
    if p0:
        print("[sleep] 提示：有 P0 补卡候选待人工确认")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
