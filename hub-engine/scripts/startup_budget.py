# 启动链字符预算门禁：四件套总和 ≤30K + 分项帽；超标退出码 1。
# 挂巡检、不挂 pre-commit（见 spec S3）。路径相对仓库根（hub-engine 的上级）。

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOTAL_LIMIT = 30_000

# (显示名, 相对仓库根路径, 单文件帽)
LIMITS: list[tuple[str, str, int]] = [
    ("AGENTS.md", "AGENTS.md", 3_000),
    ("CHARTER.md", "CHARTER.md", 3_000),
    ("WORK.md", "WORK.md", 9_000),
    ("INDEX.md", "AgentMemoryHub/INDEX.md", 14_000),
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
