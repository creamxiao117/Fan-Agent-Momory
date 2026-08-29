r"""auto_fix_lint.py — 自动修复 lint invalid 卡片的 frontmatter 缺失。

保守修复策略（只碰 frontmatter，不改正文）：
1. 缺失 type → 从父目录推断（rules/ → rule, experience/ → exp, ...）
2. 缺失 updated → 填今天日期
3. 缺失 status → active
4. tags 缺失 → 填空数组 []（tag 自动生成交给后续 LLM 流程）

所有自动修改统一写进 .sync/patches/lint-fix-<date>.md 留痕。

用法：
  python scripts/auto_fix_lint.py --root ..\AgentMemoryHub
  python scripts/auto_fix_lint.py --root ..\AgentMemoryHub --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

_LOCAL_TZ = timezone(timedelta(hours=+8))

# 父目录 → VALID_TYPES 映射
_DIR_TO_TYPE = {
    "rules": "rule",
    "methodology": "methodology",
    "longterm": "longterm",
    "experience": "exp",
    "projects": "project",
    "blueprints": "blueprint",
    "notes": "note",
    "retro": "retro",
}

from common.constants import HUMAN_REQUIRED_TYPES  # noqa: E402


def _dir_to_type(dir_name: str) -> str | None:
    return _DIR_TO_TYPE.get(dir_name)


def run_fix(root: Path, *, dry_run: bool = False) -> dict:
    """执行修复，返回统计结果。"""
    from common.frontmatter import save_card, today_date, try_read_card, validate_card
    from tools.lint import lint

    report = lint(root)
    invalid_count = report.get("invalid", 0)
    if invalid_count == 0:
        return {"fixed": 0, "failed": 0, "skipped": 0, "message": "lint 无 invalid 卡，无需修复"}

    # 收集所有需要修复的卡
    fixed_list: list[tuple[str, list[str]]] = []  # (path_str, fixes_applied)
    failed_list: list[str] = []

    for sub in _DIR_TO_TYPE:
        sub_dir = root / sub
        if not sub_dir.is_dir():
            continue
        for md in sub_dir.rglob("*.md"):
            card = try_read_card(md)
            if card is None:
                continue
            # rule/methodology 跳过自动修复（高风险，frontmatter 改动也需人工）
            if card.type in HUMAN_REQUIRED_TYPES or _dir_to_type(sub) in HUMAN_REQUIRED_TYPES:
                failed_list.append(str(md.relative_to(root)))
                continue
            errs = validate_card(card)
            if not errs:
                continue

            # 有错误 → 尝试修复
            fixes: list[str] = []
            rel_path = str(md.relative_to(root))

            if card.type not in ("rule", "exp", "note", "project", "retro", "methodology", "longterm", "blueprint"):
                new_type = _dir_to_type(sub)
                if new_type:
                    card.type = new_type
                    fixes.append(f"type: {card.type} → {new_type}")

            if not card.updated:
                card.updated = today_date()
                fixes.append(f"updated: (空) → {today_date()}")

            if card.status not in ("active", "archived", "candidate", "reference"):
                card.status = "active"
                fixes.append(f"status: {card.status or '(空)'} → active")

            if fixes:
                # 再校验一次确认修复成功
                still_errs = validate_card(card)
                if not still_errs:
                    if not dry_run:
                        save_card(card, md)
                    fixed_list.append((rel_path, fixes))
                else:
                    failed_list.append(rel_path)

    # 写 patch 留痕
    if fixed_list and not dry_run:
        patches_dir = root / ".sync" / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(_LOCAL_TZ).date().isoformat()
        patch_file = patches_dir / f"lint-fix-{today}.md"
        lines = [
            f"# auto_fix_lint 自动修复 · {today}",
            f"生成时间: {datetime.now(_LOCAL_TZ).isoformat()}",
            f"修复数量: {len(fixed_list)}",
            f"失败数量: {len(failed_list)}",
            "",
        ]
        for path, fixes in fixed_list:
            lines.append(f"- {path}")
            for f in fixes:
                lines.append(f"  - {f}")
        if failed_list:
            lines += ["", "## 修复失败（需人工）"]
            for p in failed_list:
                lines.append(f"- {p}")
        patch_file.write_text("\n".join(lines), encoding="utf-8")

    return {
        "fixed": len(fixed_list),
        "failed": len(failed_list),
        "skipped": 0,
        "details": [(str(p), fixes) for p, fixes in fixed_list],
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="auto-fix-lint", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不实际写卡")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    result = run_fix(root, dry_run=args.dry_run)

    if result["fixed"] == 0:
        print(f"[auto_fix_lint] {result.get('message', '无修复')}")
    else:
        mode = "DRY-RUN" if args.dry_run else "APPLIED"
        print(f"[auto_fix_lint] [{mode}] 修复 {result['fixed']} 张卡, 失败 {result['failed']} 张")
        for path, fixes in result.get("details", []):
            print(f"  {path}")
            for f in fixes:
                print(f"    ↳ {f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
