# 一次性迁移（2026-10-01）：把人工索引描述/注解迁回**卡 frontmatter**
# （`index_desc` / `index_note`），让 INDEX 完全由卡派生（单一真相）。
#
# 背景（计划 docs/compose/plans/2026-10-01-single-source-l0-shape.md 的 Task 3b）：
# 切到「渲染产物」前实测发现，现有 INDEX 行手里有一批信息是卡正文摘要里没有的——
#   - 9 条 `status=…｜T1 09-xx ✅` 人工追加注解（注释型）
#   - 60 条人工描述携带 ★/语言/判级 等**选型元信息**（blueprint 卡的挑选依据）
# 直接切渲染 = 丢这些信息（09-23 机械截断的教训重演）。故先迁移：
#   - 注释型 → `index_note`（精确后缀，渲染直接拼接，逐字等价）
#   - 其余差异行 → `index_desc`（旧文本逐字保留，不降级）
# 迁移后 `render_index --report` 应报「注释型 0 / 陈旧型 0」（= 渲染与现状逐字一致）。
#
# 用法（默认 dry-run，不写盘）：
#   python -m scripts.migrate_index_fields            # 打印计划
#   python -m scripts.migrate_index_fields --write    # 落盘（单写者锁内）

from __future__ import annotations

# bootstrap：让脚本可从任何 cwd 独立调用（外部调度器场景）
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # hub-engine/

import argparse  # noqa: E402
from pathlib import Path  # noqa: E402

from scripts.post_ingest_hook import extract_summary  # noqa: E402
from scripts.render_index import read_indexes  # noqa: E402
from tools.hub_registry import CardMeta, hub_root, scan  # noqa: E402

MAX_DESC = 40


def plan_fields(hub: Path, cards: list[CardMeta], old: dict[str, str]) -> dict[str, dict[str, str]]:
    """算出每张卡要补的 frontmatter 字段 → {slug: {"index_desc"/"index_note": 值}}。"""
    out: dict[str, dict[str, str]] = {}
    by_slug = {c.slug: c for c in cards}
    for slug, o in old.items():
        meta = by_slug.get(slug)
        if meta is None:
            continue
        base = extract_summary(hub / meta.rel_path, max_len=MAX_DESC)
        if o == base:
            continue
        if o.startswith(base) and o[len(base) :].strip():
            out[slug] = {"index_note": o[len(base) :]}
        else:
            out[slug] = {"index_desc": o}
    return out


def _yaml_line(key: str, value: str) -> str:
    """用 PyYAML 生成一行安全引用的 `key: value`（值含中文/引号/：都不能手拼）"""
    import yaml

    dumped = yaml.safe_dump({key: value}, allow_unicode=True, default_flow_style=False, width=10**6, sort_keys=False)
    return dumped.strip()


def _insert_fields(text: str, fields: dict[str, str]) -> str:
    """把字段插到 frontmatter 结束的 `---` 之前（保留原换行与 BOM 语义由调用方处理）。"""
    lines = text.splitlines(keepends=True)
    end = None
    seen = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            seen += 1
            if seen == 2:
                end = i
                break
    if end is None:
        raise ValueError("frontmatter 未闭合")
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    injected = [_yaml_line(k, v) + newline for k, v in fields.items()]
    return "".join(lines[:end] + injected + lines[end:])


def _has_bom(p: Path) -> bool:
    return p.read_bytes()[:3] == b"\xef\xbb\xbf"


def write_fields(hub: Path, plan: dict[str, dict[str, str]], cards: list[CardMeta]) -> int:
    """落盘（单写者锁内）。返回写入卡数。BOM/换行按原文件保留。"""
    by_slug = {c.slug: c for c in cards}
    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover - 无 sync 环境降级为无锁
        from contextlib import nullcontext as _WriteLock  # type: ignore[assignment]

    n = 0
    with _WriteLock(hub):
        for slug, fields in plan.items():
            p = hub / by_slug[slug].rel_path
            bom = _has_bom(p)
            encoding = "utf-8-sig" if bom else "utf-8"
            text = p.read_text(encoding=encoding)
            updated = _insert_fields(text, fields)
            p.write_text(updated, encoding=encoding)
            n += 1
    return n


def proofread_candidates(cards: list[CardMeta]) -> list[tuple[str, str]]:
    """迁移后仍需**人工校对**的描述：硬截断（含 `…`）/ 疑似仓库 id / 超 spec 的 40 字上限。

    这些是**迁移前就存在**的描述质量问题（非本次引入），单独列出以免它们被
    「渲染已与现状逐字一致」掩盖（零损失 ≠ 描述已合格）。
    """
    out = []
    for c in cards:
        desc = c.summary or c.title or ""
        if not desc:
            continue
        if "…" in desc or desc.startswith("gh-") or len(desc) > 45:
            out.append((c.slug, desc))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="人工索引字段回归卡片（一次性迁移）")
    ap.add_argument("--root", type=Path, default=None, help="中枢根")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run）")
    ap.add_argument("--show", type=int, default=5, help="打印前 N 条明细")
    ap.add_argument("--proofread", action="store_true", help="列出描述仍不合格（需人工校对）的卡")
    args = ap.parse_args(argv)

    hub = args.root or hub_root()
    cards = scan(hub)
    old = read_indexes(hub)
    plan = plan_fields(hub, cards, old)
    notes = [s for s, f in plan.items() if "index_note" in f]
    descs = [s for s, f in plan.items() if "index_desc" in f]
    print(f"[计划] index_note {len(notes)} 张 / index_desc {len(descs)} 张（共 {len(plan)}）")
    for slug in (notes + descs)[: args.show]:
        print(f"  {slug}\n    {plan[slug]}")
    if args.proofread:
        rows = proofread_candidates(cards)
        print(f"\n[待校对] {len(rows)} 条描述硬截断/疑 id/超 40 字（迁移前既有问题）")
        for slug, desc in rows:
            print(f"  {slug}\n    ({len(desc)}) {desc}")
    if not args.write:
        print("[dry-run] 未写盘；加 --write 落地")
        return 0
    n = write_fields(hub, plan, cards)
    print(f"[OK] 已写入 {n} 张卡的 frontmatter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
