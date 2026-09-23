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

import json
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

    print(f"快照数: {len(rows)}  区间: {rows[0]['date']} .. {rows[-1]['date']}")
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
    print("提示：'后'窗口需要 ≥2~4 周同类数据才有对比意义；届时直接重跑本脚本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
