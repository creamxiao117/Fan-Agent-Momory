# T1/状态回写入口（2026-10-01 单源改造新增）——**Agent 改索引的唯一正确姿势**。
#
# 背景：以前 T1 验证通过后，Agent 直接改 INDEX.md 的那一行（`- slug  desc｜status=active｜T1 …`）。
# 枚举迁出 L0、INDEX 变成**渲染产物**后，这种手改会被 commit 钩子（exit 6）与
# `render_index --check` 打红——不是"门禁变严"，而是那条路已经不存在了。
#
# 正确姿势：把「状态/验证」信息写进**卡自己的 frontmatter**，再让渲染器出现它：
#   - `index_note`：追加注解（T1 日期/结论/reuse）→ 渲染时逐字拼在描述后
#   - `index_desc`：覆盖描述列（少数需要人工定描述的卡）
#
# 用法：
#   python -m scripts.set_index_meta --slug typst-blueprint --note '｜status=active｜T1 09-30 ✅（3/3）'
#   python -m scripts.set_index_meta --slug typst-blueprint --desc 'Typst：排版引擎可编程化蓝图'
#   python -m scripts.set_index_meta --slug typst-blueprint --clear-note      # 清掉注解
#   python -m scripts.set_index_meta --slug typst-blueprint --dry-run        # 只打印将写什么
#
# 退出码：0 成功（含 dry-run）/ 2 卡不存在 / 3 渲染失败 / 4 参数错

from __future__ import annotations

# bootstrap：让脚本可从任何 cwd 独立调用
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # hub-engine/

import argparse  # noqa: E402
from pathlib import Path  # noqa: E402

from scripts.card_fields import remove_field, set_fields  # noqa: E402
from tools.hub_registry import CARD_DIRS, hub_root  # noqa: E402


def find_card(hub: Path, slug: str) -> Path | None:
    """按 slug 在卡目录里定位卡文件（不在则 None）。"""
    for d in CARD_DIRS:
        p = hub / d / f"{slug}.md"
        if p.exists():
            return p
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把 T1/状态注解写进卡 frontmatter 并重渲染索引")
    ap.add_argument("--slug", required=True, help="卡 slug（文件名去扩展名）")
    ap.add_argument("--note", default=None, help="追加注解（index_note，逐字拼在描述后）")
    ap.add_argument("--desc", default=None, help="覆盖描述（index_desc）")
    ap.add_argument("--clear-note", action="store_true", help="删除 index_note")
    ap.add_argument("--clear-desc", action="store_true", help="删除 index_desc")
    ap.add_argument("--root", type=Path, default=None, help="中枢根")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写盘")
    args = ap.parse_args(argv)

    if not any((args.note is not None, args.desc is not None, args.clear_note, args.clear_desc)):
        print("参数错：至少给 --note / --desc / --clear-note / --clear-desc 之一", file=sys.stderr)
        return 4

    hub = args.root or hub_root()
    card = find_card(hub, args.slug)
    if card is None:
        print(f"卡不存在：{args.slug}（在 {CARD_DIRS} 下都没找到）", file=sys.stderr)
        return 2

    actions: list[str] = []
    fields: dict[str, str] = {}
    if args.note is not None:
        fields["index_note"] = args.note
        actions.append(f"index_note = {args.note!r}")
    if args.desc is not None:
        fields["index_desc"] = args.desc
        actions.append(f"index_desc = {args.desc!r}")
    if args.clear_note:
        actions.append("删除 index_note")
    if args.clear_desc:
        actions.append("删除 index_desc")

    print(f"[卡] {card.relative_to(hub).as_posix()}")
    for a in actions:
        print(f"  - {a}")
    if args.dry_run:
        print("[dry-run] 未写盘")
        return 0

    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover - 无 sync 环境降级为无锁
        from contextlib import nullcontext as _WriteLock  # type: ignore[assignment]

    with _WriteLock(hub):
        if fields:
            set_fields(card, fields)
        if args.clear_note:
            remove_field(card, "index_note")
        if args.clear_desc:
            remove_field(card, "index_desc")

    from scripts.render_index import write as render_write

    errs = render_write(hub)
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        return 3
    print("[OK] 已写卡并重渲染索引（INDEX.md / INDEX-full.md / INDEX-experience.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
