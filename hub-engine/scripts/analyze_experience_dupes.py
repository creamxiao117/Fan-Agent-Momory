# @version V1.0 / 2026-09-23 / pi / 只读分析：experience 目录是否还有真实重复卡

"""T15（B1）经验去重的**只读**前置分析。

为什么不直接用 `scripts/deduplicate-experience.py`：
- 它无 dry-run，直接写盘（给"重复"卡前置 `<!-- DEPRECATED -->`）
- 判定靠模糊相似度（标题>0.85 / 正文>0.7），有误杀风险
- marker 目标推导有 bug（找不到 keep 就写 `merged into unknown`——本仓已有一
  张 `unknown` 卡就是它留下的）
- 非幂等：重跑会重复加 marker

本脚本只读，输出候选清单供人工裁定。

用法: python work/analyze_experience_dupes.py
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"
EXP = HUB / "experience"


def body_of(p: Path) -> str:
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    m = re.match(r"^---\s*\n.*?\n---\s*\n", raw, re.DOTALL)
    return raw[m.end() :] if m else raw


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:
    files = sorted(EXP.glob("*.md"))
    print(f"experience 卡: {len(files)}")

    # ---- ① 正文指纹完全相同（确定性重复）----
    by_hash: dict[str, list[Path]] = defaultdict(list)
    bodies: dict[Path, str] = {}
    for p in files:
        b = norm(body_of(p))
        bodies[p] = b
        if b:
            by_hash[hashlib.md5(b.encode()).hexdigest()].append(p)

    exact = {h: ps for h, ps in by_hash.items() if len(ps) > 1}
    print(f"\n① 正文完全相同（确定性重复）: {len(exact)} 组")
    for ps in exact.values():
        print("   " + "  ==  ".join(p.name for p in ps))

    # ---- ② 正文高度相似但非完全相同（需人工裁定）----
    items = [(p, bodies[p]) for p in files if len(bodies[p]) > 200]
    near: list[tuple[float, Path, Path]] = []
    for i in range(len(items)):
        pi, bi = items[i]
        for j in range(i + 1, len(items)):
            pj, bj = items[j]
            # 先便宜的后昂贵：长度差太大直接跳过
            if min(len(bi), len(bj)) / max(len(bi), len(bj)) < 0.6:
                continue
            r = SequenceMatcher(None, bi[:1500], bj[:1500]).ratio()
            if r > 0.75:
                near.append((r, pi, pj))
    near.sort(reverse=True)
    print(f"\n② 正文高度相似(>0.75，前 1500 字): {len(near)} 对")
    for r, a, b in near[:12]:
        print(f"   {r:.2f}  {a.name}")
        print(f"          {b.name}")

    # ---- ③ 标题高度相似（可能同主题不同卡）----
    print("\n③ 标题相似(>0.85):")
    titles = [(p, p.stem) for p in files]
    shown = 0
    for i in range(len(titles)):
        pi, ti = titles[i]
        for j in range(i + 1, len(titles)):
            pj, tj = titles[j]
            r = SequenceMatcher(None, ti, tj).ratio()
            if r > 0.85:
                print(f"   {r:.2f}  {pi.name}")
                print(f"          {pj.name}")
                shown += 1
    if shown == 0:
        print("   （无）")

    print("\n提示：确定性重复（①）可直接作废；②③ 须逐对人工看，禁止自动删卡。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
