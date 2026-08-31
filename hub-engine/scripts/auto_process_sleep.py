r"""auto_process_sleep.py — 自动处理已过滤的 sleep 候选。

消费 auto_sleep_filter.py 过滤后的 proposal.json（只剩 REAL 候选）：

P1 低命中候选：
  对候选查询命中的每张卡，将查询中的中文关键词作为 tag 追加到卡片 frontmatter
  （去重，不影响已有 tag），然后自动走 ingest 同步向量索引。

P0 完全未命中候选：
  生成一张草稿卡（type=exp, tags=查询关键词, 正文=简要背景 + 待人工补全），
  写入 .sync/drafts/<platform>_draft/ 目录，等待人工确认。

保守原则：只补 tag、只生成草稿——不碰规则正文、不碰方法论逻辑。
所有自动操作写 .sync/patches/sleep-process-<date>.md 留痕。

用法：
  python scripts/auto_process_sleep.py --root ..\AgentMemoryHub --date 20260829-075557
  python scripts/auto_process_sleep.py --root ..\AgentMemoryHub --since-days 3 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

_LOCAL_TZ = timezone(timedelta(hours=+8))

from common.constants import HUMAN_REQUIRED_TYPES


def _extract_cn_keywords(query: str, max_words: int = 6) -> list[str]:
    """从查询中提取中文关键词（简单分词：按标点/空格切分，保留 ≥2 字的中文段）。"""
    segs = re.split(r"[\s,，。.\-_\(\)（）\[\]【】<>《》/\\|+*#@!！?？~^&%\$]+", query)
    cn_words = []
    for s in segs:
        s = s.strip()
        if len(s) >= 2 and re.search(r"[\u4e00-\u9fff]", s):
            cn_words.append(s)
    return list(dict.fromkeys(cn_words))[:max_words]


def _check_card_type(card_path: Path) -> str | None:
    """轻量检查卡 type，避免循环内重复 import。"""
    from common.frontmatter import try_read_card
    c = try_read_card(card_path)
    return c.type if c else None


def _update_card_tags(card_path: Path, new_tags: list[str]) -> list[str]:
    """给卡追加 tag（去重），返回实际追加的 tag 列表。"""
    from common.frontmatter import save_card, try_read_card
    card = try_read_card(card_path)
    if card is None:
        return []
    existing = set(card.tags or [])
    added = [t for t in new_tags if t and t not in existing]
    if added:
        card.tags = list(card.tags or []) + added
        save_card(card, card_path)
    return added


def _generate_p0_draft(root: Path, query: str, keywords: list[str]) -> Path:
    """为 P0 候选生成草稿卡。"""
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60] or "sleep-candidate"
    now = datetime.now(_LOCAL_TZ).date().isoformat()
    frontmatter = (
        "---\n"
        f"type: exp\n"
        f"tags: [{', '.join(repr(k) for k in keywords)}]\n"
        f"updated: '{now}'\n"
        f"status: candidate\n"
        f"reuse_count: 0\n"
        "---\n\n"
    )
    body = (
        f"# {query}\n\n"
        f"来源：sleep 候选自动生成（P0 完全未命中）。\n\n"
        f"关键词：{', '.join(keywords)}\n\n"
        f"## 背景\n\n"
        f"查询词：{query}\n\n"
        f"## 待补充\n\n"
        f"- 具体场景是什么？\n"
        f"- 解决方案是什么？\n"
        f"- 相关经验或坑点？\n"
    )
    platform = "auto_sleep"
    drafts_dir = root / ".sync" / "drafts" / f"{platform}_draft"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_path = drafts_dir / f"sleep-{slug}.md"
    draft_path.write_text(frontmatter + body, encoding="utf-8")
    return draft_path


def _process_proposal(proposal_path: Path, root: Path, *, dry_run: bool = False) -> dict:
    """处理单个 proposal.json。"""
    data = json.loads(proposal_path.read_text(encoding="utf-8"))
    cands = data.get("candidates", [])
    result = {"p1_tagged": [], "p0_drafts": [], "skipped": 0}

    for c in cands:
        query = c.get("query", "")
        stage = c.get("stage", "P1-补tag别名")
        hit_paths = c.get("hit_paths") or []

        if stage.startswith("P0"):
            # P0 → 生成草稿
            keywords = _extract_cn_keywords(query)
            if not keywords:
                result["skipped"] += 1
                continue
            if not dry_run:
                draft = _generate_p0_draft(root, query, keywords)
                result["p0_drafts"].append(str(draft.relative_to(root)))
            else:
                result["p0_drafts"].append(f"(dry-run) sleep draft for: {query}")

        elif stage.startswith("P1"):
            # P1 → 给命中的卡补 tag
            keywords = _extract_cn_keywords(query)
            if not keywords or not hit_paths:
                result["skipped"] += 1
                continue
            for hp in hit_paths:
                card_path = root / hp
                if not card_path.is_file():
                    continue
                # 跳过 rule/methodology：高风险卡不自动改 frontmatter
                ctype = _check_card_type(card_path)
                if ctype in HUMAN_REQUIRED_TYPES:
                    result["skipped"] += 1
                    continue
                if not dry_run:
                    added = _update_card_tags(card_path, keywords)
                    if added:
                        result["p1_tagged"].append(f"{hp} ← {added}")
                else:
                    result["p1_tagged"].append(f"(dry-run) {hp} ← {keywords}")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(prog="auto-process-sleep", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--date", default=None, help="只处理某一天的 sleep 目录前缀（如 20260829-075557）")
    ap.add_argument("--since-days", type=int, default=3, help="最近 N 天")
    ap.add_argument("--dry-run", action="store_true", help="只分析，不写卡")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    sleep_dir = root / ".sync" / "state" / "sleep"

    if not sleep_dir.is_dir():
        print("[auto_process_sleep] sleep 目录不存在")
        return 0

    if args.date:
        targets = list(sleep_dir.glob(f"{args.date}/proposal.json"))
    else:
        cutoff = datetime.now(_LOCAL_TZ) - timedelta(days=args.since_days)
        targets = []
        for sub in sleep_dir.iterdir():
            if not sub.is_dir():
                continue
            ts_match = re.match(r"(\d{8})-(\d{6})", sub.name)
            if not ts_match:
                continue
            try:
                ts = datetime.strptime(sub.name, "%Y%m%d-%H%M%S").replace(tzinfo=_LOCAL_TZ)
            except ValueError:
                continue
            if ts >= cutoff:
                proposal = sub / "proposal.json"
                if proposal.is_file():
                    targets.append(proposal)
        targets = sorted(targets, reverse=True)

    if not targets:
        print("[auto_process_sleep] 无待处理的 proposal")
        return 0

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    total_p1 = 0
    total_p0 = 0
    for p in targets:
        result = _process_proposal(p, root, dry_run=args.dry_run)
        total_p1 += len(result["p1_tagged"])
        total_p0 += len(result["p0_drafts"])
        print(f"[auto_process_sleep] [{mode}] {p.parent.name}: P1 补 tag {len(result['p1_tagged'])}, P0 草稿 {len(result['p0_drafts'])}, 跳过 {result['skipped']}")

    # 留痕
    if (total_p1 > 0 or total_p0 > 0) and not args.dry_run:
        patches_dir = root / ".sync" / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(_LOCAL_TZ).date().isoformat()
        patch_file = patches_dir / f"sleep-process-{today}.md"
        lines = [
            f"# auto_process_sleep 自动处理 · {today}",
            f"生成时间: {datetime.now(_LOCAL_TZ).isoformat()}",
            f"P1 补 tag: {total_p1} 次",
            f"P0 生成草稿: {total_p0} 张",
        ]
        patch_file.write_text("\n".join(lines), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
