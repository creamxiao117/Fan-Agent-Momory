# 启动链字符预算门禁：四件套总和 ≤30K + 分项帽；超标退出码 1。
# 挂巡检、不挂 pre-commit（见 spec S3）。路径相对仓库根（hub-engine 的上级）。

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOTAL_LIMIT = 30_000

# (显示名, 相对仓库根路径, 单文件帽)
#
# 设计不变量：**分项帽之和 ≤ TOTAL_LIMIT**（否则总闸永远先于分项帽触发，
# 分项帽失去「防单点回潮」意义）。由 `check_limits_invariant()` 在 main() 里
# 硬校验——**不能只写在 pytest 里**（原因见下）。
#
# 2026-09-23 重新配平：INDEX 帽 14_000 → 20_000（A4 当时为压到 14K 曾用
# `slim_index --max-desc 10` 机械截断描述，INDEX 里 239/251 条变成读不懂的
# 半截词如「GitHub 仓库选…」——**省了字符但丢了信息**）。
# 现由 render_index 用卡自身描述（上限单一来源 common/index_limits，子句边界断句）；
# `slim_index` / `regen_index_desc` 已于 2026-10-01 退役（见 docs/compose/cleanup/retire-protocol.md）。
# INDEX 自然涨到 ~18K。为保证不变量，其余三项帽相应收紧。
#
# 2026-09-27 把 INDEX 帽 20k→22k 时**未同步收紧**其余三项 ⇒ 合计 31_000 > 30_000，
# 不变量被破；而当时该断言只写在 tests/test_startup_budget.py 里，pre-commit 跑的
# 正是本脚本（不看不变量）→ 照常放行，红灯在巡检里存活 4 天（09-28~10-01 全 exit=1）。
# 2026-10-01：不变量上提到本脚本硬校验（pre-commit 即可拦）。同日单源改造后
# L0 从 21.9K 降到 ~1.2K（枚举迁出 L0），总帽余量充裕，故 AGENTS 恢复 2.0k
# （实测 1.68k，足装 L2 分册指针等路由信息）。
LIMITS: list[tuple[str, str, int]] = [
    ("AGENTS.md", "AGENTS.md", 2_000),
    ("CHARTER.md", "CHARTER.md", 1_000),
    ("WORK.md", "WORK.md", 5_000),
    (
        "INDEX.md",
        "AgentMemoryHub/INDEX.md",
        12_000,
    ),  # 2026-10-01 单源改造：L0 改为「能力图」（per-card 行=0，形状由 check_l0_shape 看守）
    # 实测 ~9.4K；数字帽降为兜底（防散文回潮），不再随卡数增长、永不需人批。
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ── L1 预算（spec S2：按任务型补读的规则卡 ≤15K）─────────────────────────
# 2026-09-23 新增：此前 L0 有门禁、L1 **完全没有**，spec 声明的 ≤15K 靠自觉。
# 而真实任务必读 L1（L0+L1 才是实际上下文成本），无门禁即会重演"长卡回潮"。
L1_LIMIT = 15_000

# 卡可能所在的权威区目录（顺序即查找优先级）
_CARD_DIRS = ("rules", "methodology", "blueprints", "longterm", "projects")


def _find_card(hub: Path, slug: str) -> Path | None:
    """在权威区目录里按 slug 找卡文件"""
    for d in _CARD_DIRS:
        p = hub / d / f"{slug}.md"
        if p.exists():
            return p
    return None


def measure_tiers(root: Path | None = None) -> list[dict]:
    """量出每个任务型 L1 卡的合计字符数（含"卡不存在"清单）。

    只读。`task_tier.L1_CARDS` 是单一事实源（AGENTS.md 与它在同一口径上）。

    降级约定：若 `<root>/AgentMemoryHub` 整体不存在（例如只克隆了外层仓、
    或 CI 无嵌套仓），直接返回空列表——**"整个中枢缺失"不是预算超帽**，
    不当失败。但若中枢**存在**而某个 L1 卡名找不到文件，那是真实的
    "路由悬空"，必报（比超预算更危险）。
    """
    from tools.task_tier import l1_cards  # 局部导入：避免无 tools 环境时不可用

    hub = (root or _repo_root()) / "AgentMemoryHub"
    # 降级：无中枢目录，或中枢里连一个权威卡目录都没有 → 不视为真实中枢，
    # 直接返回空列表（"中枢未就位"不是预算超帽）。
    # 注意：不能只看 hub.is_dir()——测试夹具为放 INDEX.md 会建出空的中枢目录。
    if not hub.is_dir() or not any((hub / d).is_dir() for d in _CARD_DIRS):
        return []
    rows: list[dict] = []
    # 卡集合由卡自身 frontmatter `l1_tier` 派生（2026-10-01；不再手写清单）
    for tier, slugs in l1_cards(hub).items():
        total = 0
        missing: list[str] = []
        for s in slugs:
            p = _find_card(hub, s)
            if p is None:
                missing.append(s)
                continue
            total += len(p.read_text(encoding="utf-8-sig"))
        rows.append({"tier": tier, "chars": total, "count": len(slugs), "missing": missing})
    return rows


def check_tiers(rows: list[dict]) -> list[str]:
    """返回 L1 预算违规（空列表=通过）。

    - 单任务型合计 > L1_LIMIT → 违规（防单张长卡或堆积回潮）
    - 单任务型卡数 > L1_MAX_CARDS_PER_TIER → 违规（形状断言，2026-10-01 新增）
    - L1 卡名找不到对应文件 → 违规（路由指向不存在的卡，比超预算更危险）
    """
    from tools.task_tier import L1_MAX_CARDS_PER_TIER

    errs: list[str] = []
    for r in rows:
        if r["chars"] > L1_LIMIT:
            errs.append(f"L1[{r['tier']}] {r['chars']} > {L1_LIMIT}")
        if r["count"] > L1_MAX_CARDS_PER_TIER:
            errs.append(
                f"L1[{r['tier']}] 卡数 {r['count']} > {L1_MAX_CARDS_PER_TIER}（新增须挤掉一张：删旧卡的 l1_tier 字段）"
            )
        if r["missing"]:
            errs.append(f"L1[{r['tier']}] 卡不存在: {r['missing']}")
    return errs


def measure(root: Path) -> list[dict]:
    rows = []
    for name, rel, cap in LIMITS:
        p = root / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        rows.append({"name": name, "path": str(p), "chars": len(text), "cap": cap})
    return rows


def check(texts: dict[str, int]) -> list[str]:
    """texts: 显示名 → 字符数。返回违规消息（空列表=通过）。"""
    errs: list[str] = []
    total = 0
    for name, _rel, cap in LIMITS:
        n = texts.get(name, 0)
        total += n
        if n > cap:
            errs.append(f"{name} {n} > 分项帽 {cap}")
    if total > TOTAL_LIMIT:
        errs.append(f"启动链总和 {total} > {TOTAL_LIMIT}")
    return errs


def check_limits_invariant() -> list[str]:
    """分项帽之和 ≤ TOTAL_LIMIT（空列表=通过）。

    回归背景（2026-09-27 → 2026-10-01）：抬 INDEX 帽 20k→22k 使合计 31_000 > 30_000，
    而该断言当时只写在 pytest 里 → pre-commit（跑的就是本脚本）照常放行，
    红灯在巡检里存活 4 天无人发现。故上提到脚本自身硬校验。
    """
    total = sum(c for _name, _rel, c in LIMITS)
    if total > TOTAL_LIMIT:
        return [f"分项帽之和 {total} > 总帽 {TOTAL_LIMIT}（帽值口径违规）"]
    return []


# ── L0 形状门禁（2026-10-01：**取代人工批帽**的主门禁）──────────────────────
#
# 数字帽只能管「多大」，管不了「为什么会长」——L0 里只要有与卡数成正比的枚举行，
# 顶帽就是数学必然（先例：09-23 14k→20k、09-27 20k→22k，各只多撑 1-2 天）。
# 本断言守护的是**形状**：L0 不得出现 per-card 登记行。它与卡数无关，永远不会
# 「顶帽」，因此不需要人批；要往 L0 加枚举，门禁先红。


def check_l0_shape(text: str) -> list[str]:
    """L0（INDEX.md）形状断言：出现 per-card 登记行即违规（空列表=通过）。

    登记行正则**复用** audit_index.INDEX_ENTRY_RE（唯一权威正则）：
    其字符集不含 `/`，故能力图的目录图例行（`- rules/  35 张｜…`）天然不匹配。
    """
    from scripts.audit_index import INDEX_ENTRY_RE

    bad = [line.strip() for line in text.splitlines() if INDEX_ENTRY_RE.match(line)]
    if bad:
        return [
            f"INDEX.md 出现 {len(bad)} 条 per-card 登记行（L0 只允许能力图；"
            f"全量清单属 INDEX-full.md，由 render_index 渲染）如：{bad[0][:60]}"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="启动链 L0 + L1 预算门禁")
    ap.add_argument("--root", type=Path, default=_repo_root(), help="仓库根")
    args = ap.parse_args(argv)
    rows = measure(args.root)
    texts = {r["name"]: r["chars"] for r in rows}
    for r in rows:
        mark = "OK" if r["chars"] <= r["cap"] else "OVER"
        print(f"[{mark}] {r['name']}: {r['chars']} (cap {r['cap']})")
    total = sum(texts.values())
    print(f"[TOTAL] {total} / {TOTAL_LIMIT}")
    errs = check(texts) + check_limits_invariant()
    # L0 形状（主门禁：与卡数解耦、永不需人批）——只对真实存在的 INDEX.md 生效
    l0_path = args.root / "AgentMemoryHub" / "INDEX.md"
    if l0_path.exists():
        shape_errs = check_l0_shape(l0_path.read_text(encoding="utf-8"))
        for e in shape_errs:
            print(f"[SHAPE] {e}")
        errs += shape_errs

    # ── L1（按任务型补读）──────────────────────────────────────────────
    try:
        tier_rows = measure_tiers(args.root)
        for r in tier_rows:
            mark = "OK" if r["chars"] <= L1_LIMIT and not r["missing"] else "OVER"
            extra = f"  缺卡={r['missing']}" if r["missing"] else ""
            print(f"[{mark}] L1[{r['tier']}]: {r['chars']} (cap {L1_LIMIT}){extra}")
        errs += check_tiers(tier_rows)
    except ImportError as e:  # 无 tools 环境时降级：不把 L1 当失败
        print(f"[SKIP] L1 预算未检（无法导入 task_tier: {e}）")

    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1
    print("PASS: 启动链预算达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
