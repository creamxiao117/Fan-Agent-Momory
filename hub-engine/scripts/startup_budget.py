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
# 分项帽失去「防单点回潮」意义）。本组合计 29_000，留 1K 余量（同 spec S3）。
#
# 2026-09-23 重新配平：INDEX 帽 14_000 → 20_000（A4 当时为压到 14K 曾用
# `slim_index --max-desc 10` 机械截断描述，INDEX 里 239/251 条变成读不懂的
# 半截词如「GitHub 仓库选…」——**省了字符但丢了信息**）。
# 现改为用卡自身摘要（scripts/regen_index_desc.py，边界断句 ≤40 字），
# INDEX 自然涨到 ~18K。为保证不变量，其余三项帽相应收紧，
# 但均仍高于实际值：AGENTS 1.4K<2.5K / CHARTER 0.8K<1.5K / WORK 3.1K<5K。
LIMITS: list[tuple[str, str, int]] = [
    ("AGENTS.md", "AGENTS.md", 2_500),
    ("CHARTER.md", "CHARTER.md", 1_500),
    ("WORK.md", "WORK.md", 5_000),
    ("INDEX.md", "AgentMemoryHub/INDEX.md", 20_000),
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
    from tools.task_tier import L1_CARDS  # 局部导入：避免无 tools 环境时不可用

    hub = (root or _repo_root()) / "AgentMemoryHub"
    # 降级：无中枢目录，或中枢里连一个权威卡目录都没有 → 不视为真实中枢，
    # 直接返回空列表（"中枢未就位"不是预算超帽）。
    # 注意：不能只看 hub.is_dir()——测试夹具为放 INDEX.md 会建出空的中枢目录。
    if not hub.is_dir() or not any((hub / d).is_dir() for d in _CARD_DIRS):
        return []
    rows: list[dict] = []
    for tier, slugs in L1_CARDS.items():
        total = 0
        missing: list[str] = []
        for s in slugs:
            p = _find_card(hub, s)
            if p is None:
                missing.append(s)
                continue
            total += len(p.read_text(encoding="utf-8-sig"))
        rows.append(
            {"tier": tier, "chars": total, "count": len(slugs), "missing": missing}
        )
    return rows


def check_tiers(rows: list[dict]) -> list[str]:
    """返回 L1 预算违规（空列表=通过）。

    - 单任务型合计 > L1_LIMIT → 违规（防单张长卡或堆积回潮）
    - L1 卡名找不到对应文件 → 违规（路由指向不存在的卡，比超预算更危险）
    """
    errs: list[str] = []
    for r in rows:
        if r["chars"] > L1_LIMIT:
            errs.append(f"L1[{r['tier']}] {r['chars']} > {L1_LIMIT}")
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
    errs = check(texts)

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
