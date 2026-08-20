"""中枢每日集中审核清单 · review_today.md（抗会话归档的待审核单一来源）。

夜间/跨平台新增卡片后，把「今日需人工审核项」汇总到一个固定路径文件，
供人看一眼就知道要审什么——不依赖对话连续性、不依赖某个自动化任务汇报。

汇总三类（只读，不落卡、不写权威区）：
- **今日新增/更新卡**：权威区 `updated` == 今日（含今天刚 ingest 的卡）。
- **pending 待确认**：`.sync/pending/*.md`（rule 类待 `confirm`）。
- **今日 sleep 候选**：`.sync/state/sleep/<今日>/proposal.md`（夜间引擎提案，待采纳/忽略）。

产物：`.sync/state/review_today.md`（git-ignored 运营数据，不入提交）。

用法：
  python hub-engine/scripts/hub_review_today.py --root AgentMemoryHub          # 今日清单
  python hub-engine/scripts/hub_review_today.py --root AgentMemoryHub --json   # 结构化
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # hub-engine 加入 path

from tools.lint import _all_cards

LOCAL_TZ = timezone(timedelta(hours=+8))  # Asia/Shanghai
REVIEW_PATH = Path(".sync") / "state" / "review_today.md"


def _today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def collect_new_updated(root: Path) -> list[dict]:
    """权威区中 updated == 今日的卡（含新卡与今日改动的）"""
    today = _today_local().isoformat()
    out = []
    for sub, p, card in _all_cards(root):
        if card is None:
            continue
        if card.updated == today:
            out.append(
                {
                    "file": str(p.relative_to(root)),
                    "type": card.type,
                    "status": card.status,
                    "tags": card.tags,
                }
            )
    return out


def collect_pending(root: Path) -> list[str]:
    """.sync/pending/ 待确认的 rule 卡（相对路径）"""
    pd = root / ".sync" / "pending"
    if not pd.is_dir():
        return []
    return [p.name for p in sorted(pd.glob("*.md"))]


def collect_today_sleep(root: Path) -> list[str]:
    """今日 sleep 提案 proposal.md 路径（夜间引擎候选，待人工采纳/忽略）"""
    today = _today_local().isoformat()
    base = root / ".sync" / "state" / "sleep"
    if not base.is_dir():
        return []
    hits = [
        str(p.relative_to(base))
        for p in base.glob("*/proposal.md")
        if p.parent.name.startswith(today.replace("-", ""))
    ]
    return sorted(hits)


def render(meta: dict, new_updated: list, pending: list, sleep: list) -> str:
    today = meta["date"]
    lines = [f"# 中枢待审核清单 · {today}", ""]
    lines.append("_单一来源，抗会话归档；仅汇总不落卡。_")
    lines.append("")

    lines.append(f"## 一、今日新增/更新卡（{len(new_updated)}）")
    if new_updated:
        lines.append("| 文件 | 类型 | 状态 | tags |")
        lines.append("| --- | --- | --- | --- |")
        for c in new_updated:
            tags = ",".join(c["tags"]) if c["tags"] else "—"
            lines.append(f"| `{c['file']}` | {c['type']} | {c['status']} | {tags} |")
    else:
        lines.append("（本日无新增/更新卡）")
    lines.append("")

    lines.append(f"## 二、待确认 rule（{len(pending)}）")
    if pending:
        for p in pending:
            lines.append(f"- `{p}` → 需 `confirm` 才生效")
    else:
        lines.append("（无待确认）")
    lines.append("")

    lines.append(f"## 三、今日 sleep 候选（{len(sleep)}）")
    if sleep:
        for p in sleep:
            lines.append(f"- `.sync/state/sleep/{p}`：审核后采纳(ingest) 或 忽略")
    else:
        lines.append("（今日无夜间提案候选）")
    lines.append("")
    lines.append(
        "_审核动作：改卡 → ingest / confirm；无关 → 忽略。本清单由 hub_review_today 生成。_"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub-review-today", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--json", action="store_true", help="结构化到 stdout（不落盘）")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"中枢根目录不存在：{root}", file=sys.stderr)
        return 2

    new_updated = collect_new_updated(root)
    pending = collect_pending(root)
    sleep = collect_today_sleep(root)
    meta = {
        "date": _today_local().isoformat(),
        "new_updated": len(new_updated),
        "pending": len(pending),
        "sleep_proposals": len(sleep),
    }

    if args.json:
        print(
            json.dumps(
                {
                    "meta": meta,
                    "new_updated": new_updated,
                    "pending": pending,
                    "sleep": sleep,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    out = root / REVIEW_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(meta, new_updated, pending, sleep), encoding="utf-8")
    print(f"[review] 已生成 {out}")
    print(
        f"[review] 今日: 新增/更新卡 {meta['new_updated']} · "
        f"待确认rule {meta['pending']} · sleep候选 {meta['sleep_proposals']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
