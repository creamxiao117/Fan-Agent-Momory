#!/usr/bin/env python3
# ⚠️ 一次性脚本（已消费）—— 2026-09-23 加护栏，禁止重跑
#
# 为什么不删而是加护栏：
#   WORK.md 的 T15 曾写明「执行 python scripts/merge-methodology.py」，若不拦，
#   下一个 Agent 会照做并破坏已完成的成果。
#
# 本脚本的三个问题（已在 2026-09-23 实测确认）：
#   1. **会截断内容**：用 `content.split("---")` 取正文，而 Markdown 表格分隔行
#      `|---|` 里就含 `---`，会被切开 → 正文在第 1 个表格处被截断。
#      （实证：memory-injection-pattern.md 曾因此丢掉「5 平台对照表」与
#       「## 4. 写入规范」「## 5. 验证清单」两个小节，2026-09-23 已手工补回。）
#   2. **会覆写目标卡**：直接把合并结果写回 dst → 重跑会抹掉对 dst 的一切修正。
#   3. **非幂等**：每次运行都再给源卡前置一行 `<!-- DEPRECATED -->`。
#
# 现状：4 组合并在 2026-09-21 已完成，且已按新约定改写为
#   `status: deprecated` + `superseded_by`（不依赖注释位置）。
#   内容完整性已逐张验证（见 work/verify_merge_fidelity.py，8 张 exact）。
#
# 确需再合并新组时：请写新的幂等脚本（默认 dry-run、按 frontmatter 边界取正文、
# 不覆写已有 dst），不要复活本脚本。
import sys

_REFUSAL = """\
[REFUSED] merge-methodology.py 是一次性脚本，已消费，拒绝执行。

原因：
  1) 会用 `split("---")` 截断正文（Markdown 表格分隔行含 `---`）——
     实测曾使 memory-injection-pattern.md 丢掉两个小节，已于 2026-09-23 手工修复。
  2) 会覆写目标卡，重跑将抹掉对目标卡的所有修正。
  3) 非幂等：会重复给源卡追加 DEPRECATED 注释。

4 组合并均已完成，且已改为 `status: deprecated` + `superseded_by` 显式表达。
如需核对完整性：python work/verify_merge_fidelity.py
如需新增合并：请写幂等、默认 dry-run、不覆写 dst 的新脚本。
"""

print(_REFUSAL, file=sys.stderr)
sys.exit(2)

# --- 以下为原始实现，仅作历史留存，永不执行 ---
# Merge methodology files
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


if __name__ == "__main__":  # pragma: no cover - 护栏已在模块顶部 exit
    sys.exit(0 if main() else 1)
