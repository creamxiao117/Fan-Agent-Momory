# @version V1.0 / 2026-10-02 / pi / 一次性：为存量卡批量回填 grade（默认 dry-run）
"""migrate_grade —— 一次性迁移脚本（架构重构 M1/Task 13）。

## 映射规则（可复核，非黑盒）

| 目录 | 规则 | 产出 grade |
|---|---|---|
| `rules/` | `l1_tier` 已声明（= 该型**每任务必读**）或旧 `tier: iron` | `iron` |
| `rules/` | 含静默失败特征词 | `pitfall` |
| `rules/` | 其余 | `proven`（待 Task 14 逐张裁定是否升 iron） |
| `blueprints/` | `status: active`（= 已在本项目亲跑通过） | `proven` |
| `blueprints/` | 其余（reference/candidate） | `domain`（待验证的参考） |
| `methodology/` | 文本含静默失败特征词（假绿/静默/误报/漏报） | `pitfall` |
| `methodology/` | 其余 | `proven` |
| `longterm/` | 全部 | `domain` |
| `projects/` | 全部 | `domain` |
| `experience/` | 文本含静默失败特征词（假绿/静默失败/零报错/漏放/无任何门禁可见） | `pitfall` |
| `experience/` | 其余 | `task` |

## 纪律

- **默认 dry-run**：先出差异表（含逐条理由），人复核后再 `--apply`。
- **只动 frontmatter**：正文零 diff（脚本用行级插入，不重写正文）。
- **幂等**：已有 `grade` 的卡不动。
- **不删旧字段**：`tier` 保留一轮（Task 14 裁定后退役），避免"迁移即丢信息"。
- **iron 与 L1 互为表里**（关键设计）：iron = “该型每任务必读”，与
  `l1_tier` 声明的 L1 集合**同一件事**。故本轮把 `l1_tier` 卡回填为 `iron`
  ⇒ L1 改由 `grade=iron` 派生后集合**零漂移**（有差异表为证，见 Task 14）。
  这也保留了“单型 ≤3”的形状约束（3 code / 3 hub / 2 sync）。
- 完成使命后按 D8 协议 `git rm`（一次性脚本不留存）。

用法：
    python -m scripts.migrate_grade                # dry-run，打印差异表
    python -m scripts.migrate_grade --apply        # 落盘
    python -m scripts.migrate_grade --json         # 机器可读差异表
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.frontmatter import GRADES_BY_DIR, VALID_GRADES, try_read_card  # noqa: E402

AUTHORITY_DIRS = ("rules", "blueprints", "methodology", "longterm", "projects", "experience")

# 静默失败/假绿特征词（本机最贵的教训都属此类，见 LONGTERM/experience 卡）
PITFALL_MARKERS = (
    "假绿",
    "静默失败",
    "零报错",
    "静默跳过",
    "漏放",
    "漏报",
    "误报",
    "无法发现",
    "无人看守",
    "错误方向排查",
)

IRON_NAME_HINT = ("iron-rule",)


def classify(dir_name: str, stem: str, body: str, fm_tier: str, status: str, l1_tier: str = "") -> tuple[str, str]:
    """返回 (grade, 理由)。规则表见模块 docstring。"""
    text = body
    is_pitfall = any(m in text for m in PITFALL_MARKERS)
    if dir_name == "rules":
        if l1_tier or fm_tier == "iron" or any(h in stem for h in IRON_NAME_HINT):
            why = "l1_tier 已声明（该型必读）" if l1_tier else "旧 tier:iron 或卡名含 iron-rule"
            return "iron", why
        return (
            ("pitfall", "含静默失败特征词")
            if is_pitfall
            else (
                "proven",
                "rules/ 其余（Task 14 逐张裁定）",
            )
        )
    if dir_name == "blueprints":
        return (
            ("proven", "已在本项目亲跑（status=active）")
            if status == "active"
            else (
                "domain",
                f"未验证参考（status={status}）",
            )
        )
    if dir_name == "methodology":
        return ("pitfall", "含静默失败特征词") if is_pitfall else ("proven", "methodology/ 默认")
    if dir_name in ("longterm", "projects"):
        return "domain", f"{dir_name}/ 为环境/项目事实"
    if dir_name == "experience":
        return ("pitfall", "含静默失败特征词") if is_pitfall else ("task", "experience/ 默认")
    return "task", "未分类目录默认"


def grade_legal(dir_name: str, grade: str) -> bool:
    allowed = GRADES_BY_DIR.get(dir_name)
    return grade in VALID_GRADES and (allowed is None or grade in allowed)


def plan(root: Path) -> list[dict]:
    rows: list[dict] = []
    for d in AUTHORITY_DIRS:
        for p in sorted((root / d).glob("*.md")):
            card = try_read_card(p)
            if card is None:
                rows.append({"path": f"{d}/{p.name}", "grade": None, "why": "解析失败（跳过）", "changed": False})
                continue
            existing = str(card.extra.get("grade") or "").strip()
            grade, why = classify(
                d,
                p.stem,
                card.body,
                str(card.extra.get("tier") or ""),
                card.status,
                l1_tier=str(card.extra.get("l1_tier") or ""),
            )
            if not grade_legal(d, grade):
                rows.append({"path": f"{d}/{p.name}", "grade": grade, "why": why, "changed": False, "illegal": True})
                continue
            rows.append(
                {
                    "path": f"{d}/{p.name}",
                    "grade": existing or grade,
                    "suggested": grade,
                    "why": why,
                    "changed": not existing,
                }
            )
    return rows


def apply_one(path: Path, grade: str) -> bool:
    """在 frontmatter 末尾插入 `grade:`（正文零改动）；已有则不动。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False
    end = text.index("\n---", 3)
    fm = text[4:end]
    if re.search(r"^grade:\s*\S", fm, re.M):
        return False
    new_fm = fm.rstrip("\n") + f"\ngrade: {grade}\n"
    # 注意开头必须补回 "---\n"（fm 是 text[4:end]，已剥掉前缀四字符）——
    # 2026-10-02 实测教训：写成 "---" + fm 会产出 `---type: rule`，把 frontmatter 起始行毁掉。
    path.write_text("---\n" + new_fm + text[end + 1 :], encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="一次性：批量回填 grade")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--apply", action="store_true", help="真正落盘（默认 dry-run）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 差异表")
    args = ap.parse_args(argv)

    root = args.root or (_HUB_ENGINE.parent / "AgentMemoryHub")
    rows = plan(root)
    todo = [r for r in rows if r["changed"]]
    illegal = [r for r in rows if r.get("illegal")]
    dist = Counter(r["grade"] for r in rows if r.get("grade"))

    if args.json:
        print(json.dumps({"rows": rows, "todo": len(todo), "illegal": illegal}, ensure_ascii=False, indent=2))
    else:
        print(f"卡数 {len(rows)}｜待写 {len(todo)}｜非法映射 {len(illegal)}")
        print("grade 分布（建议值）：", dict(dist))
        for r in illegal:
            print(f"  [ILLEGAL] {r['path']} → {r['grade']}（{r['why']}）")
        for r in todo[:30]:
            print(f"  {r['path']:60s} → {r['suggested']:8s} ({r['why']})")
        if len(todo) > 30:
            print(f"  … 其余 {len(todo) - 30} 条见 --json")

    if not args.apply:
        return 0
    written = 0
    for r in todo:
        if apply_one(root / r["path"], r["suggested"]):
            written += 1
    print(f"[OK] 已写入 grade 的卡：{written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
