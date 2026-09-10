# @version V1.0 / 2026-09-11 / Hermes / 卡片 frontmatter 校验器（直接写入路径的提交前门禁）
"""卡片 frontmatter 校验器 —— 给「直接写入路径」加校验关口。

被谁调用
    1. `AgentMemoryHub/.git/hooks/pre-commit`（推荐）：提交前拦截，
       让不合规卡**进不了中枢历史**；这是唯一能覆盖「Agent 直接把 .md 写进目录」的口子。
    2. 手工/巡检：
       `python hub-engine/scripts/check_card_frontmatter.py --root AgentMemoryHub rules/a.md`

为什么需要
    2026-09-11 实测：`experience/` 下 11 张卡写 `type: experience`（非法值）静默存活数周。
    根因是「直接写入路径」没有任何校验点 —— 不走 `.sync/drafts/` 就不经过 ingest 的
    `validate_card`，而 lint 只扫 5 个权威区。本校验器把关口前移到 commit。

退出码
    0 = 全部通过（可含 dir↔type 不一致的**警告**）
    1 = 有卡不合规（阻断提交）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.frontmatter import try_read_card, validate_card

# 卡片目录 → 期望 type（仅用于**警告**：experience/ 历史上混装 rule/methodology/blueprint，
# 强制失败会造成大量假阳性）
DIR_TO_TYPE = {
    "rules": "rule",
    "blueprints": "blueprint",
    "methodology": "methodology",
    "longterm": "longterm",
    "projects": "project",
    "experience": "exp",
    "notes": "note",
}
CARD_DIRS = tuple(DIR_TO_TYPE)


def _frontmatter_start_ok(path: Path) -> bool:
    """frontmatter 必须在文件起始处（BOM 与空行容忍；游离前置行不算）"""
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    return head.startswith(b"---")


def check_file(root: Path, raw: str) -> tuple[list[str], list[str]]:
    """校验单个文件 → (errors, warnings)"""
    rel = raw.replace("\\", "/")
    path = Path(raw)
    if not path.is_absolute():
        path = root / rel
    if not path.exists():
        return [f"{rel}: 文件不存在（已删除？）"], []

    expected = DIR_TO_TYPE.get(rel.split("/")[0], "")
    if not _frontmatter_start_ok(path):
        return (
            [
                f"{rel}: frontmatter 不在文件起始处（文件必须以 '---' 开头；"
                + "代码头注释/@version 行不能放在 frontmatter 之前）"
            ],
            [],
        )

    card = try_read_card(path)
    if card is None:
        return [f"{rel}: frontmatter 无法解析（缺结束 '---' 或 YAML 语法错误）"], []

    errors = [f"{rel}: {e}" for e in validate_card(card)]
    warnings = []
    if expected and card.type != expected and not errors:
        warnings.append(
            f"{rel}: type={card.type} 与目录 '{rel.split('/')[0]}/' 期望 {expected} 不一致"
        )
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="卡片 frontmatter 校验（提交前门禁）")
    ap.add_argument("--root", required=True, help="AgentMemoryHub 根目录")
    ap.add_argument("files", nargs="+", help="待校验文件（相对 root 的路径）")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    all_errors: list[str] = []
    all_warnings: list[str] = []
    checked = 0
    for raw in args.files:
        rel = raw.replace("\\", "/")
        if rel.split("/")[0] not in CARD_DIRS or not rel.endswith(".md"):
            continue  # 非卡片文件（INDEX.md / 脚本 / 文档）不校验
        checked += 1
        errors, warnings = check_file(root, raw)
        all_errors += errors
        all_warnings += warnings

    for w in all_warnings:
        print(f"[hub-cards] ⚠️  {w}")
    if all_errors:
        print(
            f"[hub-cards] ❌ {len(all_errors)} 处 frontmatter 不合规（已检查 {checked} 张卡）："
        )
        for e in all_errors:
            print(f"  - {e}")
        print(
            "[hub-cards] 修复：python hub-engine/scripts/fix_card_schema_drift.py --root <Hub> --apply"
        )
        print(
            "[hub-cards] 说明：schema 合法值见 common/frontmatter.py 的 VALID_TYPES / VALID_STATUS"
        )
        return 1
    print(f"[hub-cards] ✅ {checked} 张卡 frontmatter 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
