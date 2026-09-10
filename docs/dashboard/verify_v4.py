# @version V1.0 / 2026-09-10 / Hermes / 看板 v4 端到端验证（DOM+交互+截图）
"""verify_v4.py - 看板 v4 自动化验证（选择器对齐真实 DOM）.

用法:
    python verify_v4.py --url http://127.0.0.1:8899/ [--shots DIR]
"""

import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

PASS, FAIL = [], []


def ck(ok: bool, name: str, extra: str = "") -> None:
    """记录一条检查结果。"""
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8899/")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    url = a.url if a.url.endswith("/") else a.url + "/"
    shots = pathlib.Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1600, "height": 1000})
        errs: list[str] = []
        bad: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("response", lambda r: bad.append(f"{r.status} {r.url[:60]}") if r.status >= 400 else None)

        pg.goto(url, wait_until="networkidle", timeout=120_000)
        pg.wait_for_timeout(2500)

        print("=== A. 错误检查 ===")
        ck(not errs, "无 JS 错误", str(errs[:2]))
        ck(not bad, "无 4xx/5xx 资源", str(bad[:2]))

        print("\n=== B. 视图切换（每个视图内容必须不同）===")
        views = pg.eval_on_selector_all(".view[data-view]", "els=>els.map(e=>e.getAttribute('data-view'))")
        sigs = {}
        for v in views:
            pg.eval_on_selector(
                f".view[data-view='{v}']",
                "e=>e.scrollTop=0",
            )
            # 用导航按钮切换（真实用户路径）
            pg.eval_on_selector_all(
                "button[data-view]",
                f"els=>{{var b=els.find(x=>x.getAttribute('data-view')==='{v}');if(b)b.click();}}",
            )
            pg.wait_for_timeout(300)
            sigs[v] = pg.eval_on_selector("#content", "e=>e.innerText.replace(/\\s+/g,' ').slice(0,600)")
            if shots:
                pg.screenshot(path=str(shots / f"view-{v}.png"), full_page=False)
        uniq = len({s for s in sigs.values() if s.strip()})
        ck(uniq == len(views), f"{len(views)} 个视图内容互不相同", f"不同签名 {uniq}/{len(views)}")
        for v, s in sigs.items():
            print(f"    {v:<10} {len(s):>4} 字  {s[:70]}")

        print("\n=== C. KPI 卡（概览）===")
        pg.eval_on_selector_all(
            "button[data-view]", "els=>{var b=els.find(x=>x.getAttribute('data-view')==='overview');if(b)b.click();}"
        )
        pg.wait_for_timeout(400)
        kpis = pg.eval_on_selector_all(
            "#kpis .card.kpi",
            "els=>els.map(e=>({lab:e.querySelector('.k-lab')?.textContent||'',val:e.querySelector('.k-val')?.textContent||''}))",
        )
        ck(len(kpis) >= 4, "KPI 卡数量 >= 4", f"found {len(kpis)}")
        empty = [
            k["lab"]
            for k in kpis
            if not k["val"].strip() or "—" in k["val"] or "undefined" in k["val"].lower() or "nan" in k["val"].lower()
        ]
        ck(not empty, "KPI 全部有真实值", f"空值: {empty}")
        print(f"    {kpis}")

        print("\n=== D. 图表 ===")
        hbars = pg.eval_on_selector_all(".hbar", "els=>els.filter(e=>e.getBoundingClientRect().width>20).length")
        charts = pg.eval_on_selector_all(
            "#chart-status svg, #chart-types svg",
            "els=>els.filter(e=>e.getBoundingClientRect().width>20).map(e=>({tag:e.tagName,kids:e.children.length}))",
        )
        ck(hbars >= 3 and len(charts) >= 1, "至少 2 个图表已渲染", f"横向条={hbars} 环形SVG={charts}")
        print(f"    {charts[:6]}")

        print("\n=== E. 表格 ===")
        for tid, need in [("tb-cron", 7), ("tb-skill", 5), ("tb-git", 2), ("tb-commits", 5)]:
            n = (
                pg.eval_on_selector(f"#{tid}", "e=>e.querySelectorAll('tr').length")
                if pg.query_selector(f"#{tid}")
                else 0
            )
            ck(n >= need, f"#{tid} 行数 >= {need}", f"rows={n}")

        print("\n=== F. 交互实测 ===")
        # 技能视图：默认只显示有引用的
        pg.eval_on_selector_all(
            "button[data-view]", "els=>{var b=els.find(x=>x.getAttribute('data-view')==='skills');if(b)b.click();}"
        )
        pg.wait_for_timeout(300)
        vis_default = pg.eval_on_selector_all("#tb-skill tr", "els=>els.length")
        checked = pg.eval_on_selector("#c-cited", "e=>e.checked") if pg.query_selector("#c-cited") else None
        # 分页后：第 1 页行数 <= 每页条数；真实筛选总数看计数文案「筛出 N / M 条」
        page_size = (
            pg.eval_on_selector("#ps-skill", "e=>parseInt(e.value,10)") if pg.query_selector("#ps-skill") else None
        )
        count_txt = pg.eval_on_selector("#c-skill", "e=>e.innerText") if pg.query_selector("#c-skill") else ""
        # 真值来自 /api/snapshot 的 skills.cited_any，不能硬编码阈值
        cited_any = pg.evaluate(
            """async () => {
            try { const r = await fetch('/api/snapshot'); const j = await r.json();
                  return (j.skills || {}).cited_any; } catch(e) { return null; }
        }"""
        )
        import re as _re

        _m = _re.search(r"(\d+)", count_txt or "")
        shown_total = int(_m.group(1)) if _m else None
        ok_rows = vis_default > 0 and (page_size is None or vis_default <= page_size)
        ok_total = (shown_total == cited_any) if (cited_any and shown_total is not None) else vis_default > 0
        ck(
            checked is True and ok_rows and ok_total,
            "技能表默认只显示有引用的（分页）",
            f"本页{vis_default}行 / 每页{page_size} / 计数「{count_txt}」 后端 cited_any={cited_any}",
        )

        # 翻页真交互：点「下页」后首行应变化 + 页码文案前进
        first_before = pg.eval_on_selector("#tb-skill tr b", "e=>e.innerText") if vis_default else None
        pg.eval_on_selector_all(
            "#pg-skill button[data-pg]",
            "els=>{var b=els.find(x=>x.innerText.indexOf('下页')>=0);if(b)b.click();}",
        )
        pg.wait_for_timeout(250)
        rows_p2 = pg.eval_on_selector_all("#tb-skill tr", "els=>els.length")
        first_after = pg.eval_on_selector("#tb-skill tr b", "e=>e.innerText") if rows_p2 else None
        page_txt = pg.eval_on_selector("#pg-skill", "e=>e.innerText") if pg.query_selector("#pg-skill") else ""
        ck(
            rows_p2 > 0 and first_after != first_before and "第2/" in page_txt.replace(" ", ""),
            "技能表分页可翻页（点下页首行变化）",
            f"p1首行={first_before!r} → p2首行={first_after!r} / {page_txt.strip()[:40]}",
        )

        # 高度体检：技能视图应压到 1~1.4 屏内（修复前 5395px≈6 屏）
        vh = pg.evaluate("()=>window.innerHeight")
        sh = pg.evaluate("()=>document.querySelector('.view[data-view=skills]').scrollHeight")
        scr = sh / vh if vh else 0
        ck(
            scr <= 1.4,
            "技能视图高度 <= 1.4 屏（修复前 6 屏）",
            f"{sh}px / {vh}px = {scr:.2f} 屏",
        )
        if shots:
            pg.screenshot(path=str(shots / "view-skills.png"), full_page=True)

        # 飞轮三项：修复前 3/4 张卡是 "—"（空）；现在应全部有真实值
        pg.eval_on_selector_all(
            "button[data-view]", "els=>{var b=els.find(x=>x.getAttribute('data-view')==='flywheel');if(b)b.click();}"
        )
        pg.wait_for_timeout(300)
        fly_vals = pg.evaluate(
            """() => Array.from(document.querySelectorAll('#kpis-fly .card.kpi')).map(e => {
                 var a = e.querySelector('.v') || e.querySelector('strong') || e;
                 return (a.innerText || '').replace(/\\s+/g, ' ').trim();
               })"""
        )
        empty = [v for v in fly_vals if "—" in v]
        card_ok = any("68" in v for v in fly_vals)
        ck(
            len(fly_vals) >= 4 and not empty and card_ok,
            "飞轮 KPI 无空卡（卡片健康应显示 68.0 而非 —）",
            f"取值={fly_vals}",
        )
        if shots:
            pg.screenshot(path=str(shots / "view-flywheel.png"), full_page=True)

        # Chat 真实回复
        pg.eval_on_selector_all(
            "button[data-view]", "els=>{var b=els.find(x=>x.getAttribute('data-view')==='chat');if(b)b.click();}"
        )
        pg.wait_for_timeout(300)
        pg.fill("#chat-in", "用一句话说明你是谁")
        pg.click("#chat-send")
        baseline = pg.eval_on_selector("#chat-log", "e=>e.innerText.length")
        reply = None
        for _ in range(60):
            pg.wait_for_timeout(1000)
            t = pg.eval_on_selector("#chat-log", "e=>e.innerText")
            if "思考中" not in t and len(t) > baseline + 10:
                reply = t
                break
        chat_txt = reply or pg.eval_on_selector("#chat-log", "e=>e.innerText")
        got = bool(reply) and "失败" not in chat_txt[-300:] and "错误" not in chat_txt[-300:]
        ck(got, "Hermes Chat 真实可用（收到模型回复）", chat_txt[-140:].replace("\n", " | "))
        if shots:
            pg.screenshot(path=str(shots / "view-chat.png"), full_page=True)

        print("\n=== G. 布局体检 ===")
        lay = pg.evaluate(
            """() => {
            var small=[], wide=[], over=[];
            document.querySelectorAll('#content *').forEach(function(e){
              var r=e.getBoundingClientRect();
              if(r.width<2||r.height<2) return;
              var fs=parseFloat(getComputedStyle(e).fontSize)||0;
              if(fs>0&&fs<12) small.push(tag(e)+':'+fs+'px');
              var inGrid = !!e.closest('.grid, .grid2, .grid3, .grid4');
              if(inGrid && r.width>1200 && r.height<110 && r.height>20) wide.push(tag(e)+':'+Math.round(r.width)+'x'+Math.round(r.height));
              if(e.scrollWidth>e.clientWidth+3&&e.clientWidth>0&&['DIV','TD','P','SPAN','TABLE'].indexOf(e.tagName)>=0) over.push(tag(e));
            });
            function tag(e){return e.tagName+(e.id?('#'+e.id):(e.className?('.'+String(e.className).split(' ')[0]):''));}
            var m=9999; document.querySelectorAll('#content *').forEach(function(e){var r=e.getBoundingClientRect(); if(r.width<2)return; var f=parseFloat(getComputedStyle(e).fontSize)||0; if(f>0&&f<m)m=f;});
            return {minFont:m, small:small.slice(0,8), smallN:small.length, wide:wide.slice(0,8), wideN:wide.length, over:over.slice(0,8), overN:over.length};
        }"""
        )
        ck(lay["minFont"] >= 12, "最小字号 >= 12px", f"{lay['minFont']}px")
        ck(lay["smallN"] <= 6, "过小字号元素 <= 6", f"{lay['smallN']} 个: {lay['small']}")
        ck(lay["wideN"] == 0, "无「小卡片占整行」", f"{lay['wideN']} 个: {lay['wide']}")
        ck(lay["overN"] == 0, "无横向溢出", f"{lay['overN']} 个: {lay['over']}")

        br.close()

    print(f"\n=== 结果: {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    for f in FAIL:
        print("  FAIL:", f)
    if shots:
        print("截图目录:", shots)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
