# @version V1.0 / 2026-09-23 / pi / 规则遵循与返工的时间序列仪表（改造前 vs 后）

"""把 `retro/snapshot-*.json` 的每日指标抽成时间序列，用于回答
「优化后的规则/方法论/门禁，实际起到了什么作用」。

为什么不直接给"改造前后对比结论"
--------------------------------
瘦身改造发生在 **2026-09-23**（今天）。'后'窗口只有 1 天，任何"改造后效果更好"
的说法都缺乏统计基础。本脚本的定位是**建立仪表 + 给出改造前基线**，
让"后"窗口积累后可直接跑同一个脚本对比——而不是先编一个结论。

代理指标（来自每日快照，均可自动采集）
--------------------------------------
门禁维度（越接近 0 越好）：
  lint_invalid / lint_schema_drift / lint_orphans / lint_ghosts / lint_stale
使用维度（越高说明规则/经验真被取用）：
  searches / hits / misses / hit_rate / reuse_ops
健康维度：overall / card / skill / flywheel / llm

用法: python work/rule_following_timeseries.py [--csv]
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

# 本文件位于 hub-engine/scripts/ → 上溯 3 层得仓库根
HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"
RETRO = HUB / "retro"

GATE_KEYS = ("invalid", "schema_drift", "orphans", "ghosts", "stale")
USE_KEYS = ("searches", "hits", "misses", "reuse_ops")
SCORE_KEYS = (
    "overall",
    "card_health",
    "skill_health",
    "flywheel_activity",
    "llm_health",
)


def _g(d, *path, default=""):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def load_lint_reports() -> list[dict]:
    """第二序列：`retro/lint-report-*.md`（08-17~09-15，覆盖改造前期）。

    ⚠️ 可比性缺口（必须声明）：报告有两种格式——
    - 旧格式（~08-27）：`孤儿页` / `无效卡片` / `幽灵登记`
    - 新格式（09-08 起）：`发现问题数`，且**新增了 long_desc / short_desc 等维度**
      （09-08 的 40 项里 34 项是 long_desc，旧格式根本不检）
    因此跨格式**不能直接比大小**；本函数同时保留可比的 `invalid`（两格式/快照同义）
    与各格式自己的“问题数”。
    """
    out: list[dict] = []
    for p in sorted(RETRO.glob("lint-report-*.md")):
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        date = p.stem.replace("lint-report-", "")
        rec = {
            "date": date,
            "fmt": "?",
            "invalid": "",
            "ghosts": "",
            "orphans": "",
            "problems": "",
            "checked": "",
        }
        m = re.search(r"^#\s*(Lint|L2)", text, re.MULTILINE)
        rec["fmt"] = "A" if (m and m.group(1) == "Lint") else "B"
        if mm := re.search(r"无效卡片[:：]\s*(\d+)", text):
            rec["invalid"] = int(mm.group(1))
        if mm := re.search(r"发现问题数[:：]\s*(\d+)", text):
            rec["problems"] = int(mm.group(1))
        if mm := re.search(r"共检查\s*(\d+)\s*张", text):
            rec["checked"] = int(mm.group(1))
        # 孤儿页 / 幽灵登记：列表项计数（“[]” 为 0）
        for key, label in (("orphans", "孤儿页"), ("ghosts", "幽灵登记")):
            if mm := re.search(rf"- {label}:\s*\[(.*?)\]", text):
                inner = mm.group(1).strip()
                rec[key] = 0 if not inner else inner.count("'") // 2
            elif mm := re.search(rf"- {label}:\n((?:\s+- .+\n)+)", text):
                rec[key] = len(re.findall(r"^\s+- ", mm.group(1), re.MULTILINE))
        out.append(rec)
    return out


def load_ingest_outcomes() -> list[dict]:
    """第三序列：`retro/log.md` 的 ingest 结果（08-17~，**定义始终未变**，最宜做趋势）。

    两种叙事标题（逐卡一条、带日期）：
      - `## [YYYY-MM-DD] ingest | 自动入区：<卡>`         → 晋升（新知识流入）
      - `## [YYYY-MM-DD] ingest | 重复内容进冲突区：<卡>` → 重复（内容/规则漂移信号）

    为何用叙事标题而非审计行 `ingest:promote`：实测两者卡名**零重叠**，
    但叙事标题是逐卡一致的流水账（各 118 条）；只看标题可避免双通道重复计数。

    conflict_rate = 重复 / (入区 + 重复)：越高说明**同一知识被反复提交**，即返工/漂移越多。
    """
    log_path = RETRO / "log.md"
    if not log_path.exists():
        return []
    per_day: dict[str, dict[str, int]] = {}
    pat = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] ingest \| (自动入区|重复内容进冲突区)")
    for line in log_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        m = pat.match(line)
        if not m:
            continue
        date, kind = m.group(1), m.group(2)
        rec = per_day.setdefault(date, {"promoted": 0, "conflict": 0})
        rec["promoted" if kind == "自动入区" else "conflict"] += 1
    out = []
    for date in sorted(per_day):
        rec = per_day[date]
        tot = rec["promoted"] + rec["conflict"]
        out.append(
            {
                "date": date,
                "promoted": rec["promoted"],
                "conflict": rec["conflict"],
                "total": tot,
                "conflict_rate": (rec["conflict"] / tot) if tot else 0.0,
            }
        )
    return out


def load_ingest_verdicts() -> list[dict]:
    """冲突条目的 **LLM 判决分布**（区分真重复 vs 判重误杀）。

    冲突条目形态：
      `## [日期] ingest | 重复内容进冲突区：<卡>（LLM 建议 <verdict>，待人工终审）`

    判决→含义（分析关键）：
      - `merge`  ← **真重复**（LLM 也认为应合并）
      - `create` ← **误杀**（LLM 认为该新建，却被去重通道拦下）
      - `review` / `skip` ← 不确定 / 放弃（既非真重复也非误杀）
      - 无括号注记 ← 早期无 LLM 判决，单列

    为何需要：单看“重复率”无法区分两种性质——
      真重复上升 = 知识被反复提交（漂移/返工成立）
      review/create 主导 = **去重门禁判不准**，性质完全不同。
    """
    log_path = RETRO / "log.md"
    if not log_path.exists():
        return []
    pat = re.compile(
        r"^## \[(\d{4}-\d{2}-\d{2})\] ingest \| 重复内容进冲突区："
        r"([^（(\n]+?)\s*(?:[（(]([^）)]*)[）)]?)?\s*$"
    )
    out: list[dict] = []
    for line in log_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        m = pat.match(line)
        if not m:
            continue
        note = (m.group(3) or "").strip()
        if "merge" in note:
            kind = "真重复"
        elif "create" in note:
            kind = "误杀"
        elif note:
            kind = "不确定"
        else:
            kind = "无注记"
        out.append({"date": m.group(1), "card": m.group(2).strip(), "kind": kind})
    return out


def load_rows() -> list[dict]:
    rows = []
    for p in sorted(RETRO.glob("snapshot-*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[WARN] 跳过不可读快照 {p.name}: {e}", file=sys.stderr)
            continue
        lint = j.get("lint") or {}
        tm = j.get("today_metrics") or {}
        hs = j.get("health_scores") or {}
        rows.append(
            {
                "date": p.stem.replace("snapshot-", ""),
                **{f"lint_{k}": lint.get(k, "") for k in GATE_KEYS},
                **{k: tm.get(k, "") for k in USE_KEYS},
                "hit_rate": tm.get("hit_rate", ""),
                "total_cards": tm.get("total_cards", ""),
                **{f"sc_{k}": hs.get(k, "") for k in SCORE_KEYS},
                "llm": hs.get("llm_health", ""),
                "alerts": len(j.get("alerts") or []),
            }
        )
    return rows


def main() -> int:
    rows = load_rows()
    if not rows:
        print("未找到快照")
        return 1

    if "--csv" in sys.argv:
        import csv

        w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        return 0

    # ── 第二序列：lint 周期报告（覆盖改造前期）────────────────────
    reps = load_lint_reports()
    print("=" * 78)
    print(f"A. 快照序列（{len(rows)} 份，{rows[0]['date']} ~ {rows[-1]['date']}）")
    print("=" * 78)
    print()
    hdr = f"{'日期':12s} {'inv':>4s} {'drift':>6s} {'orph':>5s} {'ghst':>5s} {'stale':>6s} | {'search':>7s} {'hit':>5s} {'rate':>6s} {'reuse':>6s} | {'score':>6s} {'llm':>4s} {'alerts':>7s}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['date']:12s} {r['lint_invalid']!s:>4s} {r['lint_schema_drift']!s:>6s} "
            f"{r['lint_orphans']!s:>5s} {r['lint_ghosts']!s:>5s} {r['lint_stale']!s:>6s} | "
            f"{r['searches']!s:>7s} {r['hits']!s:>5s} {r['hit_rate']!s:>6s} "
            f"{r['reuse_ops']!s:>6s} | {r['sc_overall']!s:>6s} {r['llm']!s:>4s} {r['alerts']:>7d}"
        )

    print()
    print("=" * 70)
    print("基线统计（改造前 = 全部快照；改造日 2026-09-23 仅 1 个点，不足以对比）")
    print("=" * 70)
    for key in (f"lint_{k}" for k in GATE_KEYS):
        vals = [r[key] for r in rows if isinstance(r[key], (int, float))]
        if vals:
            print(
                f"  {key:20s} 均值={sum(vals) / len(vals):6.2f}  最大={max(vals):4}  非零天数={sum(1 for v in vals if v)}"
            )
    print()
    print("=" * 78)
    print(f"B. lint 周期报告序列（{len(reps)} 份，{reps[0]['date']} ~ {reps[-1]['date']}）")
    print("=" * 78)
    print(f"{'日期':14s} {'格式':4s} {'无效卡片':>8s} {'孤儿':>5s} {'幽灵':>5s} {'问题数':>7s} {'检查卡数':>8s}")
    print("-" * 62)
    for r in reps:
        print(
            f"{r['date']:14s} {r['fmt']:4s} {r['invalid']!s:>8s} {r['orphans']!s:>5s} "
            f"{r['ghosts']!s:>5s} {r['problems']!s:>7s} {r['checked']!s:>8s}"
        )
    print()
    print("⚠️ 可比性缺口：旧格式（A）报 孤儿/无效/幽灵；新格式（B，09-08 起）报“发现问题数”")
    print("   且新增了 long_desc / short_desc 等维度（09-08 的 40 项里 34 项是 long_desc，旧格式不检）。")
    print("   ⇒ **跨格式不能直接比大小**；只有 `无效卡片/invalid` 在两格式与快照中同义可比。")

    print()
    print("=" * 78)
    print("C. 改造前后对照（改造日 = 2026-09-23）")
    print("=" * 78)

    def _num(v) -> int | None:
        return v if isinstance(v, (int, float)) else None

    pre_inv = [n for n in (_num(r["lint_invalid"]) for r in rows) if n is not None]
    pre_days = len(pre_inv)
    pre_bad = sum(1 for n in pre_inv if n > 0)

    POST = ("2026-09-23", "2026-09-24")
    post = [r for r in rows if r["date"] in POST]
    post_clean = sum(1 for r in post if all((_num(r[f"lint_{k}"]) or 0) == 0 for k in GATE_KEYS))

    print(
        f"  改造前（快照）  : {pre_days} 个有数据的天，其中 **{pre_bad} 天** invalid>0；"
        f"最大 {max(pre_inv) if pre_inv else 0}"
    )
    print(
        f"  改造前（lint 报告）: {len(reps)} 份，invalid>0 的 "
        f"{sum(1 for r in reps if isinstance(r['invalid'], int) and r['invalid'] > 0)} 份"
        f"（可比口径）；B 格式“问题数”最大值 "
        f"{max((r['problems'] for r in reps if isinstance(r['problems'], int)), default=0)}"
    )
    print(f"  改造后（后窗口）: {len(post)} 天 → 全维度均 0 的 **{post_clean} 天**")
    print()
    print(f"  结论（诚实）：**状态已确认干净**（后窗口 {post_clean}/{len(post)} 天全 0），")
    print(f"                但 **趋势尚未成立**——n={len(post)} 天不足以排除偶然。")
    print()
    print("  可证伪的判据（供 ≥2026-10-07 重跑时对照）：")
    print("    ① 正面：后窗口 ≥10 个有数据的天且 invalid/orphans/ghosts 全 0")
    print("       → 则“改造正面”成立（前提：期间检查维度未变动）")
    print("    ② 反面：任一维度复现非零 → 说明仍有未收敛的漂移源，须定位根因")
    print("    ③ 无效对比：若期间 lint 检查维度变了（如新增 long_desc），须分段比较")

    # ── D. ingest 结果趋势（定义未变，最宜做趋势）──────────────────
    ing = load_ingest_outcomes()
    print()
    print("=" * 78)
    span = f"{ing[0]['date']} ~ {ing[-1]['date']}" if ing else "-"
    print(f"D. ingest 结果趋势（{len(ing)} 个有记录的天，{span}）")
    print("=" * 78)
    if not ing:
        print("  （无数据）")
    else:
        weeks: dict[str, dict[str, int]] = {}
        for r in ing:
            y, m, d = (int(x) for x in r["date"].split("-"))
            iso = datetime.date(y, m, d).isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            w = weeks.setdefault(key, {"promoted": 0, "conflict": 0})
            w["promoted"] += r["promoted"]
            w["conflict"] += r["conflict"]
        print(f"{'周':12s} {'入区':>5s} {'重复':>5s} {'合计':>5s} {'重复率':>7s}  柱状")
        print("-" * 66)
        for k in sorted(weeks):
            w = weeks[k]
            tot = w["promoted"] + w["conflict"]
            rate = (w["conflict"] / tot) if tot else 0.0
            bar = "█" * round(rate * 30)
            print(f"{k:12s} {w['promoted']:>5d} {w['conflict']:>5d} {tot:>5d} {rate:>6.0%}  {bar}")

        tot_p = sum(r["promoted"] for r in ing)
        tot_c = sum(r["conflict"] for r in ing)
        tot = tot_p + tot_c
        if tot:
            print()
            print(f"  总计：入区 {tot_p} / 重复 {tot_c} / 合计 {tot} → 总体重复率 {tot_c / tot:.0%}")
        n_post = sum(1 for r in ing if r["date"] >= "2026-09-23")
        print()
        print("  读法：重复率高 = 同一知识被反复提交（返工/漂移）；稳定下降说明去重生效。")
        print(f"  注：改造日（2026-09-23）之后仅 {n_post} 天——仍不足以断言趋势。")

    # ── D2. 冲突判决分解（回答：重复率上升是「真重复」还是「判重误杀」）──
    verd = load_ingest_verdicts()
    if verd:
        print()
        print("=" * 78)
        print(f"E. 冲突判决分解（{len(verd)} 条冲突）")
        print("=" * 78)
        print("  为何要看：单看重复率无法区分性质——")
        print("    真重复↑ → 知识被反复提交（漂移/返工成立）；")
        print("    误杀(create) 非零 → **去重通道拦掉了本该新建的内容**（性质完全不同）。")
        print()
        vw: dict[str, dict[str, int]] = {}
        for r in verd:
            y, m, d = (int(x) for x in r["date"].split("-"))
            iso = datetime.date(y, m, d).isocalendar()
            k = f"{iso[0]}-W{iso[1]:02d}"
            vw.setdefault(k, {})
            vw[k][r["kind"]] = vw[k].get(r["kind"], 0) + 1
        kinds = ("真重复", "误杀", "不确定", "无注记")
        hdr = f"  {'周':11s} " + " ".join(f"{k:>6s}" for k in kinds) + f" {'合计':>5s} {'真重复占比':>10s}"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for k in sorted(vw):
            cw = vw[k]
            tot = sum(cw.values())
            cells = " ".join(f"{cw.get(x, 0):>6d}" for x in kinds)
            print(f"  {k:11s} {cells} {tot:>5d} {cw.get('真重复', 0) / tot:>9.0%}")

        from collections import Counter as _C

        overall = _C(r["kind"] for r in verd)
        print()
        print(
            f"  总体：真重复 {overall.get('真重复', 0)} / 误杀 {overall.get('误杀', 0)} / "
            f"不确定 {overall.get('不确定', 0)} / 无注记 {overall.get('无注记', 0)}（共 {len(verd)}）"
        )
        dup_cards = _C(r["card"] for r in verd)
        rep = sorted(((n, c) for c, n in dup_cards.items() if n > 1), reverse=True)
        if rep:
            print(f"  被反复提交的卡（≥2 次，共 {len(rep)} 个）：")
            for n, c in rep[:5]:
                print(f"    {n}×  {c}")
        print()
        print("  判据：某周真重复占比高 → 真漂移；误杀非零 → 去重拦掉了本该新建的内容。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
