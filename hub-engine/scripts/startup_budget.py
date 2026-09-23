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
    ap = argparse.ArgumentParser(description="启动链 30K 预算门禁")
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
    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1
    print("PASS: 启动链预算达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
