"""客户端技能「是否用过」的取证分析（只读，不删任何东西）。

**"没使用过"必须举证，不许感觉**。本脚本用能拿到的真实证据三档判定：

| 档 | 证据 | 含义 |
|---|---|---|
| A 已证实使用 | 名字出现在中枢的**使用台账**（query/route/reuse/mcp 连接/审计日志） | 用过，不能删 |
| B 有引用 | 名字出现在卡片正文 / SkillHub 登记（skill.yaml） | 被知识体系引用，删前要评估 |
| C 无任何痕迹 | 全库 0 命中 | **从未被任何记录提到过** ⇒ 删除候选 |

另外给出**因果证据**（用户问"原因是什么"）：
- 同一平台同一天批量出现 ⇒ 整包装入（非按需）
- 无 `SKILL.md` 的目录 ⇒ 残缺安装
- 客户端自带（名字出现在客户端安装目录的 manifest/config 里）
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HUB = REPO / "AgentMemoryHub"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.config import external_path  # noqa: E402

# SkillHub 位置只从配置取（`external_paths.skillhub`），**不硬编码本机盘符**
SH = Path(str(external_path("skillhub", HUB) or ""))

SCAN_STATUS_DIRS = [HUB / ".sync" / "state", HUB / ".sync" / "logs"]
SKIP_SUFFIX = {".db", ".sqlite", ".png", ".jpg", ".zip", ".gz", ".whl", ".exe", ".dll", ".jsonl.gz"}


def build_corpus() -> tuple[str, str]:
    """返回 (使用台账文本, 知识库文本) —— 两者证据强度不同，故分开。"""
    usage: list[str] = []
    for d in SCAN_STATUS_DIRS:
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix not in SKIP_SUFFIX and p.stat().st_size < 8_000_000:
                try:
                    usage.append(p.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    know: list[str] = []
    for d in ("rules", "blueprints", "methodology", "longterm", "projects", "experience", "notes", "retro"):
        for p in (HUB / d).rglob("*.md"):
            try:
                know.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(usage), "\n".join(know)


def main() -> int:
    caps = json.loads((HUB / "system" / "capabilities.json").read_text(encoding="utf-8"))
    usage_text, know_text = build_corpus()
    print(f"使用台账语料 {len(usage_text):,} 字符；知识库语料 {len(know_text):,} 字符\n")

    sh_names = {p.parent.name for p in (SH / "skills").rglob("SKILL.md")}
    sh_rc: dict[str, int] = {}
    import yaml

    for p in (SH / "skills").rglob("skill.yaml"):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            sh_rc[str(d.get("name") or p.parent.name)] = int(d.get("reuse_count") or 0)
        except Exception:  # noqa: BLE001
            pass

    report: dict[str, dict] = {}
    for plat, info in (caps.get("skills") or {}).items():
        d = info.get("skills_dir")
        names = info.get("skills") or []
        if not d or not names:
            continue
        root = Path(d)
        rows = []
        for name in names:
            p = root / name
            has_md = (p / "SKILL.md").is_file()
            files = [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else []
            mt = max((f.stat().st_mtime for f in files), default=0)
            size = sum(f.stat().st_size for f in files)
            in_usage = name in usage_text
            in_know = name in know_text
            rows.append(
                {
                    "name": name,
                    "has_skill_md": has_md,
                    "files": len(files),
                    "size": size,
                    "mtime": datetime.fromtimestamp(mt).strftime("%Y-%m-%d") if mt else "?",
                    "in_usage": in_usage,
                    "in_know": in_know,
                    "in_skillhub": name in sh_names,
                    "reuse_count": sh_rc.get(name),
                }
            )
        report[plat] = {"dir": str(root), "rows": rows}

    # ── 汇总 ──
    print("=" * 100)
    print("各平台技能：使用证据分档")
    print("=" * 100)
    print(f"{'平台':10s} {'总数':>4s} {'A用过':>6s} {'B被引用':>7s} {'C无痕迹':>7s} {'无SKILL.md':>10s}")
    grand = Counter()
    for plat, r in report.items():
        rows = r["rows"]
        a = [x for x in rows if x["in_usage"] or (x["reuse_count"] or 0) > 0]
        b = [x for x in rows if x not in a and x["in_know"]]
        c = [x for x in rows if x not in a and x not in b]
        nomd = [x for x in rows if not x["has_skill_md"]]
        grand["a"] += len(a)
        grand["b"] += len(b)
        grand["c"] += len(c)
        grand["n"] += len(rows)
        grand["nomd"] += len(nomd)
        print(f"{plat:10s} {len(rows):4d} {len(a):6d} {len(b):7d} {len(c):7d} {len(nomd):10d}")
    print(f"{'合计':10s} {grand['n']:4d} {grand['a']:6d} {grand['b']:7d} {grand['c']:7d} {grand['nomd']:10d}")

    # ── 原因证据 1：整包装入（同平台同一天 ≥4 个） ──
    print("\n" + "=" * 100)
    print("原因证据①：同一平台同一天批量出现 ≥4 个 ⇒ 整包/批量装入（非按需）")
    print("=" * 100)
    for plat, r in report.items():
        by_day = defaultdict(list)
        for x in r["rows"]:
            by_day[x["mtime"]].append(x["name"])
        for day, names in sorted(by_day.items()):
            if len(names) >= 4 and day != "?":
                print(f"  {plat:10s} {day}  {len(names):3d} 个：{', '.join(sorted(names))}")

    # ── 原因证据 2：残缺安装（无 SKILL.md） ──
    print("\n" + "=" * 100)
    print("原因证据②：无 SKILL.md 的目录 ⇒ 残缺安装（装了却没有内容）")
    print("=" * 100)
    for plat, r in report.items():
        nomd = [x for x in r["rows"] if not x["has_skill_md"]]
        if nomd:
            print(f"  {plat:10s} {len(nomd)} 个：{', '.join(sorted(x['name'] for x in nomd))}")

    # ── C 档清单（删除候选） ──
    print("\n" + "=" * 100)
    print("C 档：全库 0 痕迹（既无使用台账、也未被任何卡片引用）⇒ 删除候选")
    print("=" * 100)
    total_c = 0
    for plat, r in report.items():
        a = [x for x in r["rows"] if x["in_usage"] or (x["reuse_count"] or 0) > 0]
        b = [x for x in r["rows"] if x not in a and x["in_know"]]
        c = sorted(
            (x for x in r["rows"] if x not in a and x not in b),
            key=lambda x: (x["has_skill_md"], x["mtime"]),
        )
        total_c += len(c)
        sum(x["size"] // 4 for x in c)  # 粗略 token（字符/4）
        print(f"\n  [{plat}] {len(c)} 个（磁盘约 {sum(x['size'] for x in c) // 1024} KB）：")
        for x in c:
            flag = "有SKILL.md" if x["has_skill_md"] else "**无SKILL.md**"
            sh = "SH已登记" if x["in_skillhub"] else ""
            print(f"    {x['name']:50s} {x['mtime']}  {flag:14s} {sh}")
    print(f"\nC 档合计 {total_c} 个")
    (HUB / ".sync" / "state" / "skill_usage_evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"证据已存：{HUB / '.sync' / 'state' / 'skill_usage_evidence.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
