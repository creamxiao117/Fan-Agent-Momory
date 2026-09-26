r"""auto_fix_lint.py — 自动修复 lint invalid 卡片的 frontmatter 缺失。

保守修复策略（只碰 frontmatter，不改正文）：
1. 缺失 type → 从父目录推断（rules/ → rule, experience/ → exp, ...）
2. 缺失 updated → 优先取卡内 created（保留时序），无 created 才填今天
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
from datetime import date, datetime, timedelta, timezone
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

from common.constants import HUMAN_REQUIRED_TYPES


def _dir_to_type(dir_name: str) -> str | None:
    return _DIR_TO_TYPE.get(dir_name)


def _fill_updated(card, fallback: str) -> str:
    """补 updated 时优先取卡内 created（保留内容时序）。

    updated=今天会让 stale 判定失真（180 天阈值下历史卡被'刷新'成新卡）；
    取 created 保留真实时序；created 缺失或格式非法时回退 fallback。
    """
    raw = card.extra.get("created")
    if raw is None:
        return fallback
    if hasattr(raw, "isoformat"):  # yaml 会把 created: 2026-09-10 解析为 date
        return str(raw.isoformat())
    text = str(raw).strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        return fallback
    return text


def _apply_card_fixes(card, sub: str) -> list[str]:
    """对单张卡做机械修复（type/updated/status），返回修复动作描述列表。

    只改这三项、且不落盘 —— 是否落盘由调用方在**再次校验通过后**决定，
    避免把「改了一半仍然不合法」的卡写回去。
    """
    from common.frontmatter import VALID_STATUS, VALID_TYPES, today_date

    fixes: list[str] = []

    if card.type not in VALID_TYPES:
        new_type = _dir_to_type(sub)
        if new_type:
            old_type = card.type
            card.type = new_type
            fixes.append(f"type: {old_type} → {new_type}")

    if not card.updated:
        card.updated = _fill_updated(card, today_date())
        fixes.append(f"updated: (空) → {card.updated}")

    # 用 common.frontmatter.VALID_STATUS 单源（**含 deprecated**）。
    # 2026-09-25 修：这里原有一份手写四元组且漏了 deprecated ⇒ 一张
    # `status: deprecated` 的卡只要还有别的缺陷，就会被顺手改成 active。
    if card.status not in VALID_STATUS:
        old_status = card.status
        card.status = "active"
        fixes.append(f"status: {old_status or '(空)'} → active")

    return fixes


def _collect_fixable(root: Path, dry_run: bool) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """扫描权威区/非权威区 → (已修复列表, 需人工列表)。

    rule/methodology 是高风险类型（frontmatter 改动需人工），直接计入「需人工」；
    修复后**再校验一次**，仍不合法的卡也计入「需人工」（不写回半成品）。
    """
    from common.frontmatter import save_card, try_read_card, validate_card

    fixed_list: list[tuple[str, list[str]]] = []
    failed_list: list[str] = []

    for sub in _DIR_TO_TYPE:
        sub_dir = root / sub
        if not sub_dir.is_dir():
            continue
        for md in sub_dir.rglob("*.md"):
            card = try_read_card(md)
            if card is None:
                continue
            # 路径一律用 POSIX 分隔符写留痕（跨平台可读；与 post_ingest_hook 同口径）
            rel_path = md.relative_to(root).as_posix()
            # rule/methodology 跳过自动修复（高风险，frontmatter 改动也需人工）
            if card.type in HUMAN_REQUIRED_TYPES or _dir_to_type(sub) in HUMAN_REQUIRED_TYPES:
                failed_list.append(rel_path)
                continue
            if not validate_card(card):
                continue

            fixes = _apply_card_fixes(card, sub)
            if not fixes:
                continue
            if validate_card(card):
                failed_list.append(rel_path)
            else:
                if not dry_run:
                    save_card(card, md)
                fixed_list.append((rel_path, fixes))

    return fixed_list, failed_list


def _write_patch(root: Path, fixed_list: list[tuple[str, list[str]]], failed_list: list[str]) -> None:
    """写 `.sync/patches/lint-fix-<date>.md` 留痕（当日文件覆盖写）"""
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


def run_fix(root: Path, *, dry_run: bool = False) -> dict:
    """执行修复，返回统计结果。

    2026-09-25（SPLIT2）：原为单函数 130 行（C901=20），拆成
    `_apply_card_fixes` / `_collect_fixable` / `_write_patch` + 此处纯编排（复杂度降到 4）。
    """
    from tools.lint import lint

    report = lint(root)
    # 同时看非权威区漂移：experience/notes/retro 不参与 lint 的 invalid 计数，
    # 只按 invalid 判定会让漂移卡再次静默存活（2026-09-11 教训）
    invalid_count = report.get("invalid", 0) + len(report.get("schema_drift", []))
    if invalid_count == 0:
        return {
            "fixed": 0,
            "failed": 0,
            "skipped": 0,
            "message": "lint 无 invalid 卡，无需修复",
        }

    fixed_list, failed_list = _collect_fixable(root, dry_run)

    # 写 patch 留痕
    if fixed_list and not dry_run:
        _write_patch(root, fixed_list, failed_list)

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
