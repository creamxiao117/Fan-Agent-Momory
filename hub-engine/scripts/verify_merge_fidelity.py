# @version V1.0 / 2026-09-23 / pi / 校验 deprecation stub 的内容是否真已并入目标卡

"""对每张 stub，检查其正文是否被目标卡逐字包含（合并是否有损）。

判据：
- exact  : 去空白后 stub 正文是目标正文的子串 → 全文合并，可安全作废
- partial: 行级重叠率高但非全文 → 摘要式合并，作废会丢细节（需人工裁定）
- none   : 几乎无重叠 → 未真正合并，绝不可作废

用法: python work/verify_merge_fidelity.py
"""

from __future__ import annotations

import re
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"


def body_of(path: Path) -> str:
    """取 frontmatter 之后的正文；首行 DEPRECATED 注释一并剥掉"""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    raw = re.sub(r"^<!--\s*DEPRECATED[^>]*-->\s*\n+", "", raw)
    m = re.match(r"^---\s*\n.*?\n---\s*\n", raw, re.DOTALL)
    return raw[m.end() :] if m else raw


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


PAIRS = [
    ("rules/memory-hub-query-first.md", "rules/global-rules.md"),
    ("rules/context-budget-discipline.md", "rules/global-rules.md"),
    ("rules/output-language-rule.md", "rules/global-rules.md"),
    ("rules/requirement-alignment-first.md", "rules/global-rules.md"),
    ("methodology/cross-agent-memory-hub-architecture.md", "methodology/memory-injection-pattern.md"),
    ("methodology/memory-injection-mandatory-hub-query.md", "methodology/memory-injection-pattern.md"),
    ("methodology/first-principles.md", "methodology/thinking-principles.md"),
    ("methodology/occam-razor.md", "methodology/thinking-principles.md"),
    ("methodology/iteration-gate.md", "methodology/iteration-methodology.md"),
    ("methodology/phase-restart.md", "methodology/iteration-methodology.md"),
    ("methodology/feedback-loop.md", "methodology/reflection-methodology.md"),
    ("methodology/tunnel-vision-check.md", "methodology/reflection-methodology.md"),
]

print(f"{'stub':56s} {'目标':30s} 结论")
print("-" * 110)
verdicts: dict[str, int] = {}
for srel, trel in PAIRS:
    s, t = HUB / srel, HUB / trel
    if not s.exists() or not t.exists():
        print(f"{srel:56s} {trel:30s} ❌ 文件缺失")
        continue
    sb, tb = norm(body_of(s)), norm(body_of(t))
    if not sb:
        v = "empty"
    elif sb in tb:
        v = "exact"
    else:
        # 行级重叠率
        slines = [ln.strip() for ln in body_of(s).splitlines() if len(ln.strip()) > 8]
        tlines = {ln.strip() for ln in body_of(t).splitlines()}
        hit = sum(1 for ln in slines if ln in tlines)
        ratio = hit / len(slines) if slines else 0
        v = f"partial({ratio:.0%})"
    verdicts[v.split("(")[0]] = verdicts.get(v.split("(")[0], 0) + 1
    print(f"{srel:56s} {trel:30s} {v}")

print()
print("汇总:", verdicts)
print()
print("exact   → 可安全标 deprecated")
print("partial → 摘要式合并，作废会丢细节，须人工裁定")
print("none    → 未真正合并，不可作废")
