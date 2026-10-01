# 一次性迁移（2026-10-01 · Task 6）：把 L1 卡集合从**手写清单**迁到**卡自身 frontmatter**。
#
# 背景（计划 docs/compose/plans/2026-10-01-single-source-l0-shape.md 的 Task 6）：
# `tools/task_tier.L1_CARDS` 是手写枚举 + 固定帽（同 L0 INDEX 的病）——新增/退役 L1 卡
# 要改两处，必然漂移；且枚举会随卡片增长慢慢顶帽。
# 迁移后：卡自己声明 `l1_tier`（可多值），`l1_cards()` 派生集合即为真相。
#
# 字段名用 `l1_tier` 而非 `tier`：卡 frontmatter 已有 `tier: task|iron`（重要度），不得覆用。
#
# 用法（默认 dry-run）：
#   python -m scripts.migrate_l1_tier
#   python -m scripts.migrate_l1_tier --write

from __future__ import annotations

# bootstrap：让脚本可从任何 cwd 独立调用
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # hub-engine/

import argparse  # noqa: E402
from pathlib import Path  # noqa: E402

# 手写清单退出前的最后状态（迁移基准；与 tests/test_task_tier.LEGACY_L1_CARDS 同源）
LEGACY_L1_CARDS: dict[str, list[str]] = {
    "code": [
        "chinese-text-encoding-discipline",
        "agent-code-discipline-iron-rule",
        "multi-language-style-config",
    ],
    "hub": [
        "dual-platform-coherence-discipline",
        "global-rules",
        "memory-hub-distill-last",
    ],
    "sync": [
        "cross-platform-sync-rule",
        "dual-platform-coherence-discipline",
    ],
}


def plan_fields() -> dict[str, list[str]]:
    """slug → 该卡应声明的 l1_tier 列表（从手写映射反转得到）。"""
    out: dict[str, list[str]] = {}
    for tier, slugs in LEGACY_L1_CARDS.items():
        for s in slugs:
            out.setdefault(s, []).append(tier)
    return out


def _insert_field(text: str, key: str, value: list[str]) -> str:
    """把 `key: [a, b]` 插到 frontmatter 结束的 `---` 之前（保留原换行）。"""
    lines = text.splitlines(keepends=True)
    seen = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            seen += 1
            if seen == 2:
                newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
                rendered = f"{key}: [{', '.join(value)}]{newline}" if len(value) > 1 else f"{key}: {value[0]}{newline}"
                return "".join(lines[:i] + [rendered] + lines[i:])
    raise ValueError("frontmatter 未闭合")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="L1 卡集合迁移到手写→卡声明（一次性）")
    ap.add_argument("--root", type=Path, default=None, help="中枢根")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run）")
    args = ap.parse_args(argv)

    hub = args.root or _P(__file__).resolve().parents[2] / "AgentMemoryHub"
    plan = plan_fields()
    print(f"[计划] 给 {len(plan)} 张卡写 l1_tier：{plan}")

    if not args.write:
        print("[dry-run] 未写盘；加 --write 落地")
        return 0

    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover
        from contextlib import nullcontext as _WriteLock  # type: ignore[assignment]

    written = 0
    with _WriteLock(hub):
        for slug, tiers in plan.items():
            p = hub / "rules" / f"{slug}.md"
            if not p.exists():
                print(f"[warn] 找不到卡：{p}")
                continue
            raw = p.read_bytes()
            bom = raw[:3] == b"\xef\xbb\xbf"
            encoding = "utf-8-sig" if bom else "utf-8"
            p.write_text(_insert_field(raw.decode(encoding), "l1_tier", tiers), encoding=encoding)
            written += 1
    print(f"[OK] 已写入 {written} 张卡的 l1_tier")
    return 0


if __name__ == "__main__":
    sys.exit(main())
