# 一次性校对（2026-10-01）：修「描述质量」的**系统性成因**，剩下的列给人工。
#
# 背景：Task 3b 迁移后实测 142 条描述不合格（硬截断 `…` / 仅仓库 id / 超 spec 40 字）。
# 这些都是**迁移前既有**的问题（不是本次引入），但它们会随渲染进入 L2 分册，
# 而 blueprints/ 的用途就是「立项时挑范式」——描述读不懂等于蓝图层失效。
#
# 分类与处置（只做**信息不丢**的自动改）：
#   A. 描述就是仓库 id（`gh-xxx`）→ 用卡 H1（作者写的一句话）；无 H1 → 留人工
#   B. 描述里混着 `status=/（T1 …` 注解 → **拆**成 index_desc + index_note（都保留）
#   C. 硬截断 `…` 且有 H1 → 用 H1（H1 是完整句，不是被砍的半句）
#   D. 其余（无 H1 可退、纯超长手写描述）→ **不自动改**，列清单给人工
#
# 用法（默认 dry-run）：
#   python -m scripts.proofread_index_desc              # 分类统计 + 待人工清单
#   python -m scripts.proofread_index_desc --write      # 写回 index_desc / index_note

from __future__ import annotations

# bootstrap：让脚本可从任何 cwd 独立调用
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # hub-engine/

import argparse  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from scripts.card_fields import set_fields  # noqa: E402
from scripts.post_ingest_hook import cut_at_boundary  # noqa: E402
from tools.hub_registry import SUMMARY_MAX_BY_DIR, CardMeta, hub_root, scan  # noqa: E402

MAX_DESC = 40


def _limit_for(dir_name: str) -> int:
    """该目录的描述上限（蓝图 800，其余 250）——**与校验侧同一单源**（common/index_limits）。"""
    return SUMMARY_MAX_BY_DIR.get(dir_name, MAX_DESC)


_ID_RE = re.compile(r"^gh-[A-Za-z0-9.\-]+$")
# 注解起点：这些片段属于「状态/验证」信息，不该混进描述列（会被 40 字截断吃掉）
_SUFFIX_RE = re.compile(r"(?:｜?status=|。status=|（T1|—— status=|｜T1)")


def _h1(card_path: Path) -> str:
    """卡正文首个 `# ` 标题（无则空串）。"""
    for line in card_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):  # 只认 H1
            return ""
    return ""


def classify(hub: Path, cards: list[CardMeta]) -> dict[str, list[tuple[str, str, dict]]]:
    """→ {分类: [(slug, 现描述, 建议字段)]}；建议字段为空 dict = 需人工。"""
    groups: dict[str, list[tuple[str, str, dict]]] = {
        "A_id_to_h1": [],
        "B_split_note": [],
        "C_cut_to_h1": [],
        "D_manual": [],
    }
    for c in cards:
        desc = c.summary or ""
        if not desc:
            continue
        h1 = _h1(hub / c.rel_path)
        limit = _limit_for(c.dir)
        if _ID_RE.match(desc):
            (groups["A_id_to_h1"] if h1 else groups["D_manual"]).append(
                (c.slug, desc, {"index_desc": cut_at_boundary(h1, limit)} if h1 else {})
            )
            continue
        m = _SUFFIX_RE.search(desc)
        if m:
            head = desc[: m.start()].rstrip("。 ")
            note = desc[m.start() :]
            fields = {"index_desc": cut_at_boundary(head, limit), "index_note": note}
            groups["B_split_note"].append((c.slug, desc, fields))
            continue
        if "…" in desc and h1 and len(desc) < len(h1):
            # 现描述是被砍的半句、H1 是作者写的完整句 → 换 H1（现在不再有 40 字硬切）
            groups["C_cut_to_h1"].append((c.slug, desc, {"index_desc": cut_at_boundary(h1, limit)}))
            continue
        if "…" in desc or len(desc) > limit:
            groups["D_manual"].append((c.slug, desc, {}))
    return groups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="索引描述质量校对（一次性）")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--write", action="store_true", help="写回 index_desc / index_note（默认 dry-run）")
    ap.add_argument("--show", type=int, default=6, help="每类打印条数")
    args = ap.parse_args(argv)

    hub = args.root or hub_root()
    cards = scan(hub)
    groups = classify(hub, cards)
    labels = {
        "A_id_to_h1": "A 描述只是仓库 id → 改用卡 H1",
        "B_split_note": "B 描述混着 status/T1 注解 → 拆成 desc + note",
        "C_cut_to_h1": "C 描述硬截断 → 改用卡 H1",
        "D_manual": "D 需人工（不自动改）",
    }
    for key, label in labels.items():
        rows = groups[key]
        print(f"\n[{label}] {len(rows)}")
        for slug, old, new in rows[: args.show]:
            print(f"  {slug}\n    old: {old}\n    new: {new}")
        if len(rows) > args.show:
            print(f"    …（共 {len(rows)}）")

    auto = groups["A_id_to_h1"] + groups["B_split_note"] + groups["C_cut_to_h1"]
    if not args.write:
        print(f"\n[dry-run] 可自动改 {len(auto)} 条；未写盘（加 --write）")
        return 0

    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover
        from contextlib import nullcontext as _WriteLock  # type: ignore[assignment]

    by_slug = {c.slug: c for c in cards}
    written = 0
    with _WriteLock(hub):
        for slug, _old, fields in auto:
            if not fields:
                continue
            set_fields(hub / by_slug[slug].rel_path, fields)
            written += 1
    print(f"[OK] 已改写 {written} 条（index_desc / index_note）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
