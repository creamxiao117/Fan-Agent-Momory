# @version V1.0 / 2026-09-11 / Hermes / 卡片 schema 漂移外科式修复器（保留 EOL/created）
"""卡片 schema 漂移外科式修复器（幂等，默认 dry-run）。

背景（2026-09-11 实测）：
    experience/ 下 11 张卡写 `type: experience`（非法值）+ 缺 `updated`，静默存活数周；
    同类漂移 2026-08-29 已修过 23 张后复发。根因是「直接写卡进目录」绕过 ingest 校验，
    且 experience/notes/retro 不在 lint 的权威区扫描内（现由 tools/lint.find_schema_drift 覆盖）。

与 auto_fix_lint.py 的分工：
    - auto_fix_lint.py ：走 save_card() 重渲染 frontmatter（规范字段序）+ 写 patch 留痕，
                        高风险类型（rule/methodology）直接跳过。
    - 本脚本         ：逐行外科式改写（最小 diff、保留原 EOL）、默认覆盖非权威区、
                        补 updated 时取卡内 created（保留内容时序）。

修复项（只碰 frontmatter，不动正文）：
    1. type 非法 → 按所在目录映射（rules→rule / experience→exp / blueprints→blueprint …）
    2. updated 缺失 → 取卡内 created；无 created 才用今天
    3. status 非法 → active
    4. 无 frontmatter / frontmatter 无法解析 → 只报告（需人工，不臆造）

用法：
  python scripts/fix_card_schema_drift.py --root ..\\AgentMemoryHub
  python scripts/fix_card_schema_drift.py --root ..\\AgentMemoryHub --apply
  python scripts/fix_card_schema_drift.py --root ..\\AgentMemoryHub --include-high-risk
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.constants import HUMAN_REQUIRED_TYPES
from common.frontmatter import VALID_TYPES, today_date, try_read_card, validate_card
from tools.lint import AUTHORITY_DIRS, NON_AUTHORITY_DIRS

# 目录 → 合法 type（与 engine.config.yaml / sync.py TYPE_DIR 口径一致）
DIR_TO_TYPE = {
    "rules": "rule",
    "blueprints": "blueprint",
    "methodology": "methodology",
    "longterm": "longterm",
    "projects": "project",
    "experience": "exp",
    "notes": "note",
}

VALID_STATUS = ("active", "archived", "candidate", "reference")
_TYPE_RE = re.compile(r"^type:[ \t]*(\S+)[ \t]*$")
_STATUS_RE = re.compile(r"^status:[ \t]*(\S+)[ \t]*$")
_UPDATED_RE = re.compile(r"^updated:[ \t]*\S+")
_CREATED_RE = re.compile(r"^created:[ \t]*(.+?)[ \t]*$")


def _fm_bounds(lines: list[str]) -> tuple[int, int] | None:
    """返回 frontmatter 首行/末行分隔符下标；无法解析时 None"""
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first is None or lines[first].strip() != "---":
        return None
    for i in range(first + 1, len(lines)):
        if lines[i].strip() == "---":
            return first, i
    return None


def _eol(line: str) -> str:
    return "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")


def _clean(raw: str) -> str:
    text = raw.strip()
    for q in ('"', "'"):
        if len(text) >= 2 and text.startswith(q) and text.endswith(q):
            return text[1:-1]
    return text


def _iso_or_none(text: str) -> str | None:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def repair(
    path: Path, dir_type: str | None, apply: bool, today: str
) -> tuple[list[str], str | None]:
    """返回 (修复动作, 跳过原因)；跳过原因非空表示需人工"""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lines = fh.read().splitlines(keepends=True)

    bounds = _fm_bounds(lines)
    if bounds is None:
        return [], "无 frontmatter（需人工补，非机械可修）"
    _, end = bounds

    actions: list[str] = []
    created: str | None = None
    has_updated = False
    last_insert = bounds[0]

    for i in range(bounds[0] + 1, end):
        body = lines[i].rstrip("\r\n")
        if _CREATED_RE.match(body):
            created = _iso_or_none(_clean(_CREATED_RE.match(body).group(1)))  # type: ignore[union-attr]
        if _UPDATED_RE.match(body):
            has_updated = True
        m = _TYPE_RE.match(body)
        if m and m.group(1) not in VALID_TYPES and dir_type:
            eol = _eol(lines[i])
            lines[i] = f"type: {dir_type}{eol}"
            actions.append(f"type: {m.group(1)} → {dir_type}")
        m = _STATUS_RE.match(body)
        if m and m.group(1) not in VALID_STATUS:
            eol = _eol(lines[i])
            lines[i] = f"status: active{eol}"
            actions.append(f"status: {m.group(1)} → active")
        if body.startswith(("type:", "tags:", "status:", "updated:", "reuse_count:")):
            last_insert = i

    if not has_updated:
        value = created or today
        eol = _eol(lines[end])
        lines.insert(last_insert + 1, f"updated: '{value}'{eol}")
        actions.append(
            f"updated: 补 {value}" + ("" if created else "（无 created，用今天）")
        )

    if actions and apply:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("".join(lines))
    return actions, None


def run_fix(
    root: Path, *, apply: bool = False, include_high_risk: bool = False
) -> dict:
    """扫描并（可选）修复；返回统计与明细"""
    today = today_date().isoformat()
    fixed: list[tuple[str, list[str]]] = []
    skipped: list[tuple[str, str]] = []
    clean = 0

    for sub in AUTHORITY_DIRS + NON_AUTHORITY_DIRS:
        d = root / sub
        if not d.is_dir():
            continue
        dir_type = DIR_TO_TYPE.get(sub)
        for md in sorted(d.glob("*.md")):
            if md.name == "log.md" or md.name.startswith("lint-report-"):
                continue
            if md.name.startswith("."):
                continue
            # 高风险类型（rule/methodology）默认跳人工；--include-high-risk 才动
            if not include_high_risk and (
                dir_type in HUMAN_REQUIRED_TYPES or sub in ("rules", "methodology")
            ):
                continue
            rel = str(md.relative_to(root))
            with open(md, encoding="utf-8-sig", newline="") as fh:
                head = fh.read(4000)
            if not head.startswith("---") and not head.lstrip("\ufeff").startswith(
                "---"
            ):
                skipped.append((rel, "frontmatter 不在文件起始处（可能有游离前置行）"))
                continue
            card = try_read_card(md)
            if card is None:
                skipped.append((rel, "frontmatter 无法解析"))
                continue
            if not validate_card(card):
                clean += 1
                continue
            actions, skip_reason = repair(md, dir_type, apply, today)
            if skip_reason:
                skipped.append((rel, skip_reason))
            elif actions:
                fixed.append((rel, actions))

    return {
        "apply": apply,
        "today": today,
        "clean": clean,
        "fixed": len(fixed),
        "skipped": len(skipped),
        "details": fixed,
        "skipped_details": skipped,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="fix-card-schema-drift", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--apply", action="store_true", help="真正写盘（缺省 dry-run）")
    ap.add_argument(
        "--include-high-risk",
        action="store_true",
        help="同时处理 rules/ methodology/（默认跳过，需人工）",
    )
    args = ap.parse_args()

    res = run_fix(
        Path(args.root).resolve(),
        apply=args.apply,
        include_high_risk=args.include_high_risk,
    )
    mode = "APPLIED" if res["apply"] else "DRY-RUN"
    print(
        f"[fix_card_schema_drift] [{mode}] 合规 {res['clean']} 张 / 修复 {res['fixed']} 张 / 需人工 {res['skipped']} 张"
    )
    for rel, actions in res["details"]:
        print(f"  {rel}")
        for a in actions:
            print(f"    ↳ {a}")
    for rel, reason in res["skipped_details"]:
        print(f"  ⚠️ {rel} → {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
