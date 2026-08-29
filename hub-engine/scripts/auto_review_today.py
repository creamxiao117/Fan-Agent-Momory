"""auto_review_today.py -- 对 review_today.md 按卡片 type 分类自动过/留。

review_today.md 由 hub_review 步骤生成，列出当日新增 / 更新 / 待审核的卡片。
本脚本按 type 分类决策：

必留人工审核（自动跳过）：
  - rules / methodology 类卡（覆盖全局行为，一条坏规则影响所有任务）

自动确认（标记为已审核，写 REVIEW_AUTO_CONFIRMED.md）：
  - experience / longterm / projects / blueprints / notes 类卡
    （声明性内容，不影响检索质量，可安全跳过人工审核）

用法：
  python scripts/auto_review_today.py --root ../AgentMemoryHub
  python scripts/auto_review_today.py --root ../AgentMemoryHub --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

_LOCAL_TZ = timezone(timedelta(hours=+8))

# 这些 type 需要人工审核
from common.constants import HUMAN_REQUIRED_TYPES as _HUMAN_REQUIRED_TYPES


def _extract_card_type_from_review_line(line: str) -> str | None:
    """从 review_today.md 的一行中提取卡片 type。"""
    # 格式示例：- [rule] rules/xxx.md  或  - rules/xxx.md
    m = re.search(r"\[(rule|methodology|exp|note|project|retro|blueprint|longterm)\]", line)
    if m:
        return m.group(1)
    m = re.search(r"(rules|methodology|experience|longterm|projects|blueprints|notes)/", line)
    if m:
        dir_to_type = {
            "rules": "rule",
            "methodology": "methodology",
            "experience": "exp",
            "longterm": "longterm",
            "projects": "project",
            "blueprints": "blueprint",
            "notes": "note",
        }
        return dir_to_type.get(m.group(1))
    return None


def _parse_review_today(review_path: Path) -> dict:
    """解析 review_today.md 内容。"""
    if not review_path.is_file():
        return {"exists": False}
    text = review_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    human_keep = []
    auto_pass = []
    other = []

    for line in lines:
        if not line.strip().startswith("-"):
            other.append(line)
            continue
        ctype = _extract_card_type_from_review_line(line)
        if ctype is None:
            other.append(line)
        elif ctype in _HUMAN_REQUIRED_TYPES:
            human_keep.append((line, ctype))
        else:
            auto_pass.append((line, ctype))

    return {
        "exists": True,
        "human_keep": human_keep,
        "auto_pass": auto_pass,
        "other": other,
        "raw": text,
    }


def run_review(root: Path, *, dry_run: bool = False) -> dict:
    review_path = root / ".sync" / "state" / "review_today.md"
    parsed = _parse_review_today(review_path)

    if not parsed.get("exists"):
        return {"message": "review_today.md 不存在，跳过自动分类", "auto_pass": 0, "human_keep": 0}

    if parsed["auto_pass"] and not dry_run:
        ignored = review_path.parent / "REVIEW_AUTO_CONFIRMED.md"
        lines = [
            "# auto_review_today 自动确认清单",
            f"确认时间: {datetime.now(_LOCAL_TZ).isoformat()}",
            f"共 {len(parsed['auto_pass'])} 条自动过审",
            "",
        ]
        for line, ctype in parsed["auto_pass"]:
            lines.append(f"- [{ctype}] {line.strip().lstrip('- ')}")
        ignored.write_text("\n".join(lines), encoding="utf-8")

    return {
        "auto_pass": len(parsed["auto_pass"]),
        "human_keep": len(parsed["human_keep"]),
        "human_details": [(l.strip(), t) for l, t in parsed["human_keep"]],
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="auto-review-today", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--dry-run", action="store_true", help="只分类，不写自动确认清单")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    result = run_review(root, dry_run=args.dry_run)

    if "message" in result:
        print(f"[auto_review_today] {result['message']}")
        return 0

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"[auto_review_today] [{mode}] 自动过审 {result['auto_pass']} 条, 留人工 {result['human_keep']} 条")
    for line, ctype in result.get("human_details", []):
        print(f"  HUMAN | [{ctype}] {line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
