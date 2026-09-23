#!/usr/bin/env python3
# Merge methodology files
import sys
from pathlib import Path

import yaml

METHODOLOGY_PATH = Path(
    r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/methodology"
)

MERGE_PAIRS = [
    ("first-principles.md", "occam-razor.md", "thinking-principles.md"),
    ("iteration-gate.md", "phase-restart.md", "iteration-methodology.md"),
    ("tunnel-vision-check.md", "feedback-loop.md", "reflection-methodology.md"),
    (
        "cross-agent-memory-hub-architecture.md",
        "memory-injection-mandatory-hub-query.md",
        "memory-injection-pattern.md",
    ),
]


def merge_files(src1, src2, dst):
    print(f"Merge: {src1} + {src2} -> {dst}")

    with open(METHODOLOGY_PATH / src1, "r", encoding="utf-8") as f:
        content1 = f.read()
    with open(METHODOLOGY_PATH / src2, "r", encoding="utf-8") as f:
        content2 = f.read()

    parts = []
    p1 = content1.split("---")
    if len(p1) >= 3:
        try:
            meta = yaml.safe_load(p1[1])
            meta["updated"] = "2026-09-21"
            meta["source"] = f"merged from {src1}, {src2}"
            parts.append("---")
            for k, v in meta.items():
                if isinstance(v, list):
                    parts.append(f"{k}:")
                    for i in v:
                        parts.append(f"- {i}")
                else:
                    parts.append(f"{k}: {v}")
            parts.append("---")
            parts.append("")
        except (yaml.YAMLError, AttributeError, TypeError) as e:
            print(f"  [WARN] frontmatter 解析失败，跳过 meta: {e}")

    parts.append(f"## {src1}\n")
    if len(p1) >= 3:
        parts.append(p1[2].strip())
    parts.append("\n\n## " + src2 + "\n")
    p2 = content2.split("---")
    if len(p2) >= 3:
        parts.append(p2[2].strip())

    with open(METHODOLOGY_PATH / dst, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    for src in [src1, src2]:
        with open(METHODOLOGY_PATH / src, "r", encoding="utf-8") as f:
            old = f.read()
        with open(METHODOLOGY_PATH / src, "w", encoding="utf-8") as f:
            f.write(f"<!-- DEPRECATED: merged into {dst} -->\n\n" + old)

    print("  [OK] Done")
    return True


def main():
    print("=" * 60)
    print("Merge Methodology Cards")
    print("=" * 60)
    count = sum(1 for s1, s2, d in MERGE_PAIRS if merge_files(s1, s2, d))
    print("=" * 60)
    print(f"Completed: {count} pairs merged")
    return count == len(MERGE_PAIRS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
