# @version V1.0 / 2026-09-17 / Hermes / conflicts 区 17 组逐组裁决 dry-run 清单
"""只读取证：扫 .sync/conflicts/ 全部未决卡，逐组产出裁决依据与建议处置。

输出：retro/conflicts-adjudication-20260917.md（+ stdout 简表）
不修改任何权威区文件、不删除任何 conflicts 文件。
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

HUB = Path("C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub")
CONFLICTS = HUB / ".sync" / "conflicts"
AUTHORITY = ["rules", "blueprints", "methodology", "longterm", "projects"]
NON_AUTH = ["experience", "notes"]

TYPE2DIR = {
    "rule": "rules",
    "blueprint": "blueprints",
    "methodology": "methodology",
    "longterm": "longterm",
    "project": "projects",
    "exp": "experience",
    "note": "notes",
    "retro": "retro",
}


def read_fm(text: str) -> dict:
    m = re.match(r"(?s)^---\r?\n(.*?)\r?\n---", text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(("-", " ")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def norm(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def find_authority(slug: str) -> list[Path]:
    hits = []
    for d in AUTHORITY + NON_AUTH:
        f = HUB / d / f"{slug}.md"
        if f.exists():
            hits.append(f)
    return hits


def main() -> None:
    mds = sorted(p for p in CONFLICTS.glob("*.md"))
    rows = []
    detail = []
    for md in mds:
        stem = md.stem  # 形如 trae_<slug>
        platform, _, slug = stem.partition("_")
        text = norm(md)
        fm = read_fm(text)
        ctype = fm.get("type", "?")
        cstatus = fm.get("status", "?")
        cdate = fm.get("updated", "?")

        pred_f = md.with_suffix(".pred.json")
        dec = {}
        if pred_f.exists():
            try:
                raw = json.loads(pred_f.read_text(encoding="utf-8"))
                dec = raw.get("decision", raw) or {}
            except ValueError:
                dec = {}
        action = dec.get("action", "无判决")
        conf = dec.get("confidence", None)
        target = dec.get("target") or "-"
        reason = (dec.get("reason") or "-")[:60]

        auth = find_authority(slug)
        if auth:
            same = norm(auth[0]) == text
            n_a, n_c = len(norm(auth[0]).splitlines()), len(text.splitlines())
            if same:
                verdict = "真重复（权威区已有同 slug 且正文逐字节相同）→ 可丢弃"
            else:
                diff_lines = sum(
                    1
                    for l in difflib.unified_diff(norm(auth[0]).splitlines(), text.splitlines(), lineterm="")
                    if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
                )
                verdict = (
                    f"同名不同文（权威 {n_a} 行 / 冲突 {n_c} 行，±{diff_lines} 行）"
                    "→ 必须逐组 diff 判旧版/更全版/互补，禁止直接删"
                )
        else:
            verdict = "权威区无同名卡 → 查重通过，可直接入区"

        if action == "review" and (conf or 0) == 0:
            kind = "降级误判（网关/解析失败）"
        elif action in ("merge", "delete"):
            kind = f"LLM 真判决 {action}（保守落冲突区，待人工）"
        elif action == "skip":
            kind = "LLM 真判决 skip（须先确认是否真重复）"
        elif action == "create":
            kind = "LLM 真判决 create（未被采纳？）"
        else:
            kind = "无判决（pred.json 缺失）"

        rows.append((platform, slug, ctype, cstatus, action, conf, target, kind))
        detail.append(
            f"### {platform}_{slug}\n\n"
            f"- 卡型/状态/日期：`{ctype}` / `{cstatus}` / `{cdate}`\n"
            f"- LLM 判决：`action={action}` `confidence={conf}` `target={target}`\n"
            f"- reason：{reason}\n"
            f"- 查重结论：{verdict}\n"
            f"- 类型路由目标：`{TYPE2DIR.get(ctype, '?')}/`\n"
        )

    lines = [
        "# conflicts 区未决卡裁决清单（dry-run，只读取证）",
        "",
        "- 生成：2026-09-17 · Hermes cron",
        f"- 未决组数：**{len(mds)}**（另有 4 个已裁决归档目录：_resolved_20260827 / _resolved_20260902 / resolved_20260906 / resolved_20260910）",
        "- 本文件仅为裁决依据，不含任何删除或搬移动作",
        "",
        "| # | platform | slug | 类型 | 状态 | action | conf | target | 判决性质 |",
        "|--:|:--|:--|:--|:--|:--|--:|:--|:--|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    lines += ["", "---", "", "## 逐组依据", ""] + detail
    out = HUB / "retro" / "conflicts-adjudication-20260917.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"写入 {out}")
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}. {r[0]:<9} {r[1][:52]:<54} {r[2]:<11} {r[4]:<8} {r[5]!s:<5} {r[7][:28]}")


if __name__ == "__main__":
    main()
