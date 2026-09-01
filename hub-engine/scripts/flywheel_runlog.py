"""flywheel-runlog：记录每一圈飞轮的时间戳/输入/产出，生成时间线 JSON 供可视化回放。

用法:
  python flywheel_runlog.py record   --hub-root <中枢> --skillhub-root <SkillHub> --stage <run|flywheel|register|smoke> --input-str <输入> --output-str <输出> [--ok|--fail]
  python flywheel_runlog.py timeline --hub-root <中枢> --skillhub-root <SkillHub> [--output <HTML路径>] [--json-out <JSON路径>]
  python flywheel_runlog.py list     --hub-root <中枢> --skillhub-root <SkillHub> [--limit 50]

存储位置:
  <SkillHub>/work/flywheel/runlog/runlog.jsonl    （每圈一条 JSONL）
  <SkillHub>/work/flywheel/runlog/
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STAGES = ["run", "flywheel", "register", "smoke"]
STAGE_LABEL = {
    "run": "🚀 完整飞轮",
    "flywheel": "📥 飞轮触发（草稿→ingest）",
    "register": "📦 技能注册（卡→SkillHub）",
    "smoke": "✅ T1 验证（smoke test）",
}


def runlog_dir(skillhub_root: Path) -> Path:
    """返回 runlog 存储目录。"""
    d = skillhub_root / "work" / "flywheel" / "runlog"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runlog_path(skillhub_root: Path) -> Path:
    """返回 runlog.jsonl 文件路径。"""
    return runlog_dir(skillhub_root) / "runlog.jsonl"


def append_record(skillhub_root: Path, record: dict) -> Path:
    """追加一条记录到 JSONL。"""
    p = runlog_path(skillhub_root)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p


def load_records(skillhub_root: Path, limit: int = 500) -> list[dict]:
    """读取所有 runlog 记录（按时间正序，最多 limit 条）。"""
    p = runlog_path(skillhub_root)
    if not p.is_file():
        return []
    records = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    # 按 ts 排序
    records.sort(key=lambda r: r.get("ts", ""))
    if len(records) > limit:
        records = records[-limit:]
    return records


def make_record(stage: str, input_str: str, output_str: str, ok: bool, extra: dict | None = None) -> dict:
    """构造一条 runlog 记录。"""
    now = datetime.now().astimezone()
    return {
        "ts": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "stage": stage,
        "stage_label": STAGE_LABEL.get(stage, stage),
        "input": input_str[:500] if input_str else "",
        "output": output_str[:1000] if output_str else "",
        "ok": bool(ok),
        **(extra or {}),
    }


def group_by_run(records: list[dict]) -> list[list[dict]]:
    """按 run 分组：一次完整 run 包含 run → flywheel → register → smoke 的串联子阶段。

    简单策略：以 run 记录为组头，之后连续的 flywheel/register/smoke 归入同一组，
    直到遇到下一个 run 记录为止。
    """
    groups = []
    current = []
    for r in records:
        if r["stage"] == "run":
            if current:
                groups.append(current)
            current = [r]
        else:
            current.append(r)
    if current:
        groups.append(current)
    return groups


def print_list(records: list[dict], limit: int) -> None:
    """打印 runlog 列表。"""
    if not records:
        print("(暂无记录)")
        return
    recent = records[-limit:] if limit < len(records) else records
    print(f"共 {len(records)} 条记录，展示最近 {len(recent)} 条:\n")
    for r in recent:
        status = "✅" if r.get("ok") else "❌"
        print(f"  {r.get('ts', '?')[:19]}  {status}  {r.get('stage_label', r.get('stage'))}")
        if r.get("input"):
            print(f"      输入: {r['input'][:80]}")
        if r.get("output"):
            print(f"      输出: {r['output'][:80]}")
        print()


def build_timeline_html(records: list[dict], html_path: Path) -> None:
    """生成飞轮可视化回放 HTML 时间线。"""
    groups = group_by_run(records)

    # 统计
    total_runs = len([g for g in groups if g and g[0]["stage"] == "run"])
    total_stages = len(records)
    ok_count = sum(1 for r in records if r.get("ok"))
    success_rate = round(ok_count / max(total_stages, 1) * 100, 1)

    # 按天统计
    by_day = defaultdict(lambda: {"total": 0, "ok": 0})
    for r in records:
        d = r.get("date", "?")
        by_day[d]["total"] += 1
        if r.get("ok"):
            by_day[d]["ok"] += 1

    # 渲染时间线条目
    def fmt_ts(ts: str) -> str:
        try:
            return ts.replace("T", " ")[:19]
        except (AttributeError, IndexError):
            return ts

    timeline_items = []
    for _idx, r in enumerate(reversed(records[-200:])):  # 最多显示 200 条，倒序（最新在上）
        status_cls = "ok" if r.get("ok") else "fail"
        tag_dot = "dot ok" if r.get("ok") else "dot fail"
        safe_input = (r.get("input") or "").replace("<", "&lt;").replace(">", "&gt;")
        safe_output = (r.get("output") or "").replace("<", "&lt;").replace(">", "&gt;")
        item = f"""
            <li class="tl-item tl-{status_cls}">
              <div class="tl-time">{fmt_ts(r.get("ts", "?"))}</div>
              <div class="tl-body">
                <div class="tl-title"><span class="{tag_dot}"></span>{r.get("stage_label", r.get("stage"))}</div>
                {f'<div class="tl-io"><strong>输入：</strong>{safe_input[:120]}</div>' if safe_input else ""}
                {f'<div class="tl-io tl-out"><strong>输出：</strong>{safe_output[:200]}</div>' if safe_output else ""}
              </div>
            </li>
        """
        timeline_items.append(item)
    tl_html = (
        "\n".join(timeline_items)
        if timeline_items
        else '<li class="tl-empty">暂无运行记录，运行 <code>python flywheel.py run</code> 开始第一圈</li>'
    )

    # 按天统计柱状
    day_keys = sorted(by_day.keys())[-14:]
    day_bars = []
    for k in day_keys:
        s = by_day[k]
        pct = round(s["ok"] / max(s["total"], 1) * 100)
        color = "#3d8b5e" if pct >= 80 else ("#c79a3b" if pct >= 50 else "#c94f4f")
        w = min(s["total"] * 12, 100)
        day_bars.append(f"""
            <div class="daybar">
              <div class="daybar-label">{k[5:]}</div>
              <div class="daybar-track"><div class="daybar-fill" style="width:{w}%;background:{color}">{s["ok"]}/{s["total"]}</div></div>
            </div>
        """)
    daybars_html = "\n".join(day_bars) if day_bars else '<div class="tl-empty">暂无数据</div>'

    # 完整圈数统计
    full_runs = [g for g in groups if g and g[0]["stage"] == "run"]
    full_run_items = ""
    for i, g in enumerate(reversed(full_runs[-20:])):
        run_id = len(full_runs) - i
        head = g[0]
        stages_html = " → ".join(
            [
                f'<span class="chip {"chip-ok" if s.get("ok") else "chip-fail"}">{s.get("stage_label", "")}</span>'
                for s in g
            ]
        )
        status = "✅" if head.get("ok") else "❌"
        full_run_items += f"""
        <div class="run-card">
          <div class="run-head"><strong>#{run_id} 飞轮</strong> {status} <span class="muted">{fmt_ts(head.get("ts", "?"))}</span></div>
          <div class="run-stages">{stages_html}</div>
          <div class="run-io">{head.get("input", "")[:80]} → {head.get("output", "")[:80]}</div>
        </div>
        """

    # 近 7 天活跃数
    _now = datetime.now().astimezone()
    seven_days_ago = (_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)).strftime("%Y-%m-%d")
    recent_7d = sum(1 for r in records if r.get("date", "") >= seven_days_ago)
    recent_7d_w = min(recent_7d * 5, 100)

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>飞轮运行时间线回放</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--paper:#f5f5f5;--paper-2:#fff;--ink:#2d3142;--muted:#4f5d75;--soft:#7a8399;
  --rule:rgba(45,49,66,0.12);--rule-strong:rgba(45,49,66,0.24);
  --accent:#eb6c36;--ok:#3d8b5e;--warn:#c79a3b;--crit:#c94f4f;}}
*{{box-sizing:border-box}}
body{{background:var(--paper);color:var(--ink);font-family:'Geist',sans-serif;font-size:13px;line-height:1.55;margin:0;padding:32px 24px 48px}}
.wrap{{max-width:1080px;margin:0 auto}}
.eyebrow{{font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.14em;color:var(--muted);text-transform:uppercase;margin-bottom:6px}}
h1{{font-family:'Instrument Serif',serif;font-size:28px;font-weight:400;letter-spacing:-0.01em;margin:0}}
.sub{{color:var(--muted);margin-top:4px;font-size:12px}}
.meta{{display:flex;gap:12px;margin-top:10px;flex-wrap:wrap}}
.meta span{{font-family:'Geist Mono',monospace;font-size:10px;padding:3px 8px;background:var(--paper-2);border:1px solid var(--rule);border-radius:4px;color:var(--soft)}}
.grid{{display:grid;gap:16px;margin-top:28px}}
.grid.hero{{grid-template-columns:1.2fr 1fr 1fr 1fr}}
.grid.two{{grid-template-columns:1fr 1.3fr}}
@media(max-width:800px){{.grid.hero,.grid.two{{grid-template-columns:1fr}}}}
.card{{background:var(--paper-2);border:1px solid var(--rule);border-radius:6px;padding:20px}}
.card h3{{font-size:14px;font-weight:600;margin:0 0 4px}}
.card .val{{font-family:'Instrument Serif',serif;font-size:36px;font-weight:400;line-height:1.05}}
.card .unit{{font-size:12px;color:var(--muted);margin-left:4px}}
.hero-score{{font-family:'Instrument Serif',serif;font-size:56px;font-weight:400;line-height:1}}
.hero-score .pct{{font-size:24px;color:var(--muted)}}
.progress{{height:8px;background:rgba(45,49,66,0.08);border-radius:4px;margin-top:10px;overflow:hidden}}
.progress .bar{{height:100%;border-radius:4px}}
.dot{{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:middle}}
.dot.ok{{background:var(--ok)}}.dot.fail{{background:var(--crit)}}.dot.coral{{background:var(--accent)}}
.muted{{color:var(--soft);font-size:11px}}

/* Timeline */
.timeline{{list-style:none;padding:0;margin:0;position:relative}}
.timeline::before{{content:"";position:absolute;left:92px;top:4px;bottom:4px;width:2px;background:var(--rule)}}
.tl-item{{display:flex;gap:12px;padding:10px 0;position:relative}}
.tl-time{{width:84px;flex-shrink:0;font-family:'Geist Mono',monospace;font-size:10px;color:var(--soft);padding-top:4px;text-align:right}}
.tl-body{{flex:1;background:var(--paper-2);border:1px solid var(--rule);border-radius:6px;padding:12px 14px}}
.tl-item.tl-ok .tl-body{{border-left:3px solid var(--ok)}}
.tl-item.tl-fail .tl-body{{border-left:3px solid var(--crit)}}
.tl-title{{font-weight:600;font-size:12px;margin-bottom:6px}}
.tl-io{{font-size:11px;color:var(--muted);margin-top:4px;word-break:break-all}}
.tl-io.tl-out{{color:var(--ink);opacity:.8}}
.tl-empty{{padding:40px;text-align:center;color:var(--soft);font-style:italic;font-size:12px}}

/* 日统计柱状 */
.daybar{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.daybar-label{{width:48px;font-family:'Geist Mono',monospace;font-size:10px;color:var(--muted);text-align:right}}
.daybar-track{{flex:1;height:20px;background:rgba(45,49,66,0.06);border-radius:3px;overflow:hidden}}
.daybar-fill{{height:100%;color:#fff;font-size:10px;padding:2px 8px;font-weight:600;display:flex;align-items:center;white-space:nowrap}}

/* Run card */
.run-card{{padding:12px 14px;border:1px solid var(--rule);border-radius:6px;margin-bottom:10px;background:var(--paper-2)}}
.run-head{{font-size:12px;margin-bottom:8px}}
.run-head strong{{font-size:13px}}
.run-head .muted{{margin-left:8px}}
.run-stages{{margin-bottom:6px}}
.run-io{{font-size:11px;color:var(--muted);word-break:break-all}}
.chip{{display:inline-block;padding:2px 8px;border-radius:10px;font-family:'Geist Mono',monospace;font-size:9px;margin-right:4px}}
.chip-ok{{background:rgba(61,139,94,0.10);color:var(--ok);border:1px solid var(--ok)}}
.chip-fail{{background:rgba(201,79,79,0.10);color:var(--crit);border:1px solid var(--crit)}}

footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--rule);font-family:'Geist Mono',monospace;font-size:10px;color:var(--soft);display:flex;justify-content:space-between}}
code{{background:rgba(45,49,66,0.06);padding:1px 5px;border-radius:3px;font-family:'Geist Mono',monospace;font-size:11px}}
</style></head><body>
<div class="wrap">
  <header>
    <div class="eyebrow">FLYWHEEL · TIMELINE REPLAY</div>
    <h1>飞轮运行时间线回放</h1>
    <p class="sub">按时间顺序展示每一圈飞轮的执行过程，支持审计与复盘</p>
    <div class="meta">
      <span>生成时间：{generated_at}</span>
      <span>记录总数：{total_stages}</span>
      <span>完整飞轮圈数：{total_runs}</span>
      <span>成功率：{success_rate}%</span>
    </div>
  </header>

  <div class="grid hero">
    <div class="card" style="background:rgba(235,108,54,0.08);border-color:var(--accent)">
      <div class="eyebrow" style="color:var(--accent)">OVERALL</div>
      <div class="hero-score">{total_stages}<span class="pct"> 阶段</span></div>
      <div class="progress"><div class="bar" style="width:{min(max(success_rate, 0), 100)}%;background:var(--accent)"></div></div>
      <div class="muted" style="margin-top:8px"><span class="dot coral"></span>{total_runs} 圈完整飞轮 · 成功率 {success_rate}%</div>
    </div>
    <div class="card">
      <div class="eyebrow">SUCCESS</div>
      <div class="val">{ok_count}<span class="unit">/ {total_stages}</span></div>
      <div class="progress"><div class="bar" style="width:{success_rate}%;background:var(--ok)"></div></div>
      <div class="muted" style="margin-top:8px">成功阶段数</div>
    </div>
    <div class="card">
      <div class="eyebrow">FULL RUNS</div>
      <div class="val">{total_runs}<span class="unit"> 圈</span></div>
      <div class="progress"><div class="bar" style="width:{min(total_runs * 20, 100)}%;background:var(--accent)"></div></div>
      <div class="muted" style="margin-top:8px">完整闭环飞轮数</div>
    </div>
    <div class="card">
      <div class="eyebrow">RECENT 7D</div>
      <div class="val">{recent_7d}<span class="unit"> 阶段</span></div>
      <div class="progress"><div class="bar" style="width:{recent_7d_w}%;background:var(--muted)"></div></div>
      <div class="muted" style="margin-top:8px">近 7 天活跃度</div>
    </div>
  </div>

  <div class="grid two" style="margin-top:24px">
    <div class="card">
      <div class="eyebrow">DAILY RUNS</div>
      <h3>每日运行统计 · 近 14 天</h3>
      <div style="margin-top:12px">{daybars_html}</div>
    </div>
    <div class="card">
      <div class="eyebrow">FULL FLYWHEEL RUNS</div>
      <h3>最近 {len(full_runs[-20:])} 圈完整飞轮</h3>
      <div style="margin-top:12px">{full_run_items if full_run_items else '<div class="tl-empty">暂无完整飞轮记录</div>'}</div>
    </div>
  </div>

  <div class="card" style="margin-top:24px">
    <div class="eyebrow">TIMELINE</div>
    <h3>运行时间线 · 最近 200 阶段（最新在上）</h3>
    <ul class="timeline" style="margin-top:16px">{tl_html}</ul>
  </div>

  <footer>
    <span>flywheel-timeline.html · 飞轮可视化回放</span>
    <span>数据源：SkillHub/work/flywheel/runlog/runlog.jsonl</span>
  </footer>
</div>
</body></html>
"""
    html_path.write_text(html, encoding="utf-8")


def cmd_record(args: argparse.Namespace) -> int:
    """子命令 record：追加一条运行记录。"""
    skillhub_root = Path(args.skillhub_root).resolve()
    if args.stage not in STAGES:
        print(f"[error] stage 必须是以下之一: {STAGES}", file=sys.stderr)
        return 2
    extra = {}
    if args.extra_json:
        try:
            extra = json.loads(args.extra_json)
        except json.JSONDecodeError as e:
            print(f"[warn] --extra-json 解析失败: {e}")
    rec = make_record(
        args.stage,
        args.input_str or "",
        args.output_str or "",
        args.ok,
        extra,
    )
    p = append_record(skillhub_root, rec)
    status = "✅" if args.ok else "❌"
    print(f"[ok] {status} 已记录: {rec['stage_label']}  → {p}")
    return 0


def build_timeline_data(records: list[dict]) -> dict:
    """构建供 hub-health.html 读取的 JSON 数据结构。"""
    groups = group_by_run(records)
    total_runs = len([g for g in groups if g and g[0]["stage"] == "run"])
    total_stages = len(records)
    ok_count = sum(1 for r in records if r.get("ok"))
    success_rate = round(ok_count / max(total_stages, 1) * 100, 1)

    by_day = defaultdict(lambda: {"total": 0, "ok": 0})
    for r in records:
        d = r.get("date", "?")
        by_day[d]["total"] += 1
        if r.get("ok"):
            by_day[d]["ok"] += 1

    full_runs = [g for g in groups if g and g[0]["stage"] == "run"]

    # 近 7 天
    _now = datetime.now().astimezone()
    seven_days_ago = (_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)).strftime("%Y-%m-%d")
    recent_7d = sum(1 for r in records if r.get("date", "") >= seven_days_ago)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_stages": total_stages,
        "total_runs": total_runs,
        "ok_count": ok_count,
        "success_rate": success_rate,
        "recent_7d": recent_7d,
        "by_day": sorted(by_day.items()),
        "full_runs": full_runs[-20:],  # 最近 20 圈
        "records": records[-200:],  # 最近 200 条
    }


def cmd_timeline(args: argparse.Namespace) -> int:
    """子命令 timeline：生成 HTML 回放页，并输出供 hub-health.html 读取的 JSON 数据。"""
    skillhub_root = Path(args.skillhub_root).resolve()
    records = load_records(skillhub_root)
    out = Path(args.output).resolve() if args.output else (skillhub_root / "work" / "flywheel" / "timeline.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    build_timeline_html(records, out)
    print(f"[ok] 时间线 HTML 已生成: {out}")
    print(
        f"     共 {len(records)} 条记录，"
        f"{len([g for g in group_by_run(records) if g and g[0]['stage'] == 'run'])} 圈完整飞轮"
    )

    # 输出 JSON 数据文件（与 HTML 同目录，供 hub-health.html fetch）
    data = build_timeline_data(records)
    data_path = out.with_name("flywheel-timeline-data.json")
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 飞轮时间线数据 JSON: {data_path}")

    if args.json_out:
        jp = Path(args.json_out).resolve()
        jp.parent.mkdir(parents=True, exist_ok=True)
        groups = group_by_run(records)
        jp.write_text(
            json.dumps(
                {
                    "records": records,
                    "groups": groups,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[ok] 原始数据 JSON: {jp}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """子命令 list：列出最近运行记录。"""
    skillhub_root = Path(args.skillhub_root).resolve()
    records = load_records(skillhub_root)
    print_list(records, args.limit)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flywheel-runlog", description="飞轮运行日志与可视化时间线回放")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("record", help="追加一条运行记录")
    pr.add_argument("--stage", required=True, choices=STAGES)
    pr.add_argument("--hub-root", default="")
    pr.add_argument("--skillhub-root", required=True)
    pr.add_argument("--input-str", default="")
    pr.add_argument("--output-str", default="")
    pr.add_argument("--extra-json", default="")
    ok_grp = pr.add_mutually_exclusive_group()
    ok_grp.add_argument("--ok", dest="ok", action="store_true", default=True)
    ok_grp.add_argument("--fail", dest="ok", action="store_false")
    pr.set_defaults(func=cmd_record)

    pt = sub.add_parser("timeline", help="生成 HTML 时间线回放")
    pt.add_argument("--hub-root", default="")
    pt.add_argument("--skillhub-root", required=True)
    pt.add_argument("--output", default="", help="HTML 输出路径")
    pt.add_argument("--json-out", default="", help="JSON 数据输出路径")
    pt.set_defaults(func=cmd_timeline)

    pl = sub.add_parser("list", help="列出最近运行记录")
    pl.add_argument("--hub-root", default="")
    pl.add_argument("--skillhub-root", required=True)
    pl.add_argument("--limit", type=int, default=50)
    pl.set_defaults(func=cmd_list)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
