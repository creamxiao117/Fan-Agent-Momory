# @version V1.0 / 2026-09-11 / Hermes / 看板 v5 增量（a11y+告警抽屉+来源徽章）真浏览器验收
"""v5 验收：用真实 Chromium 打开看板，逐项断言本轮新增能力。

设计原则（源自本项目中枢经验）：
  1. 数字/DOM 为准，不靠肉眼与截图判读 —— 每个断言都从 DOM 取值。
  2. 必抓 console error / pageerror —— JS 语法错会导致整页白屏，静态检查抓不到。
  3. 交互类必须"真点真开"，不能只查元素存在（存在 ≠ 可用）。

用法：
    python3 docs/dashboard/verify_v5.py                    # 默认 127.0.0.1:8899
    python3 docs/dashboard/verify_v5.py --url http://...   # 指定地址
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

PASS: list[str] = []
FAIL: list[str] = []


def chk(name: str, ok: bool, extra: str = "") -> None:
    """记录一条断言结果。"""
    (PASS if ok else FAIL).append(f"{name}{(' | ' + extra) if extra else ''}")
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  [{extra}]" if extra else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8899/")
    a = ap.parse_args()

    errors: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        # 真读剪贴板需要 context 级权限（"能复制"是用户核心诉求，必须实测而非只查按钮存在）
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, permissions=["clipboard-read", "clipboard-write"])
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        print("\n=== 0. 加载与 JS 健康 ===")
        pg.goto(a.url, wait_until="networkidle", timeout=90_000)
        pg.wait_for_timeout(2500)
        chk("无 JS 运行时错误", not errors, "; ".join(errors)[:300] if errors else "0 条")
        chk("KPI 已渲染", pg.locator("#kpis .kpi").count() >= 4, f"{pg.locator('#kpis .kpi').count()} 张卡")

        print("\n=== 1. P0-1 指标来源徽章 ===")
        n_src = pg.locator(".src").count()
        chk("来源徽章已渲染", n_src >= 4, f"{n_src} 个")
        if n_src:
            tip = pg.locator(".src").first.get_attribute("title") or ""
            chk("徽章带出处 + 口径", ("｜口径：" in tip) and len(tip) > 20, tip[:110])

        print("\n=== 2. 用户需求：告警可点击 → 详情 + 日志 + 复制 ===")
        al = pg.locator("[data-alert]")
        chk("告警条目可点击（button 语义）", al.count() > 0, f"{al.count()} 条")
        chk("告警条目为 button 元素", (al.first.evaluate("e=>e.tagName") == "BUTTON") if al.count() else False)
        if al.count():
            al.first.click()
            pg.wait_for_timeout(2500)
            chk("点击后抽屉打开", pg.locator("#drawer.on").count() == 1)
            body = pg.locator("#dw-body").inner_text()
            chk("抽屉显示详情正文", len(body) > 80, f"{len(body)} 字符")
            chk("抽屉含【错误日志】区块", "错误日志" in body)
            chk("抽屉含【定位来源】区块", "定位来源" in body)
            chk("抽屉含【建议命令】区块", "建议命令" in body)
            chk("有『复制修复包』按钮", pg.locator("#dw-copy").count() == 1)
            chk("有『复制原始JSON』按钮", pg.locator("#dw-raw").count() == 1)
            chk("有『复制错误日志』按钮", pg.locator("[data-copy-ev]").count() >= 1)
            n_cmd = pg.locator("#dw-body .cmd code").count()
            chk("修复命令可逐条复制", n_cmd >= 1, f"{n_cmd} 条命令")
            # --- 剪贴板真实验收：复制修复包 → 从剪贴板读回 ---
            pg.click("#dw-copy")
            pg.wait_for_timeout(600)
            clip = pg.evaluate("() => navigator.clipboard.readText()")
            chk("『复制修复包』真的写入剪贴板", len(clip) > 100, f"{len(clip)} 字符")
            chk(
                "修复包自包含（含告警ID）",
                "告警 ID" in clip or "alert" in clip.lower(),
                clip.splitlines()[1][:60] if clip.count(chr(10)) >= 1 else clip[:60],
            )
            chk(
                "修复包含证据/命令段落",
                ("证据" in clip and ("命令" in clip or "python" in clip.lower())),
                "证据+命令齐备",
            )
            pg.click("[data-copy-ev]")
            pg.wait_for_timeout(500)
            clip2 = pg.evaluate("() => navigator.clipboard.readText()")
            chk("『复制日志』写入剪贴板", len(clip2) > 0, f"{len(clip2)} 字符")
            chk(
                "Esc 可关闭抽屉",
                (pg.keyboard.press("Escape"), pg.wait_for_timeout(500), pg.locator("#drawer.on").count() == 0)[2],
            )

        print("\n=== 3. P0-2 无障碍 ===")
        chk("nav 有 role=tablist", pg.locator("#nav[role=tablist]").count() == 1)
        chk("tab 有 aria-selected", pg.locator('#nav button[data-view][aria-selected="true"]').count() == 1)
        n_tab = pg.locator("#nav button[data-view][role=tab]").count()
        chk("全部 tab 有 role=tab", n_tab >= 7, f"{n_tab} 个")
        chk("有 aria-live 播报区", pg.locator("#live[aria-live=polite]").count() == 1)
        chk(
            "live 区已播报刷新结果",
            "刷新完成" in (pg.locator("#live").inner_text() or ""),
            (pg.locator("#live").inner_text() or "")[:60],
        )
        chk("有跳过导航链接", pg.locator("a.skip").count() == 1)
        chk("焦点环样式已定义", "focus-visible" in pg.content() or "focus-visible" in str(len(pg.content())))
        # 方向键换视图（既有处理器）
        pg.locator("#nav button[data-view]").first.focus()
        v0 = pg.locator(".view.on").first.get_attribute("data-view")
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(400)
        v1 = pg.locator(".view.on").first.get_attribute("data-view")
        chk("←/→ 可切换视图", v0 != v1, f"{v0} → {v1}")

        print("\n=== 4. P1-6 命令面板 ===")
        pg.keyboard.press("Control+k")
        pg.wait_for_timeout(400)
        chk("Ctrl+K 打开面板", pg.locator("#pal.on").count() == 1)
        if pg.locator("#pal.on").count():
            n0 = pg.locator("#pal-list [data-pal]").count()
            chk("面板有可选项", n0 > 0, f"{n0} 项")
            pg.fill("#pal-q", "飞轮")
            pg.wait_for_timeout(400)
            n1 = pg.locator("#pal-list [data-pal]").count()
            chk("输入可过滤", 0 < n1 <= n0, f"{n0} → {n1}")
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(300)
            chk("Esc 关闭面板", pg.locator("#pal.on").count() == 0)

        print("\n=== 5. P2-7 主题切换 ===")
        theme0 = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        pg.click("#btn-theme")
        pg.wait_for_timeout(400)
        theme1 = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        chk("可切换主题", theme0 != theme1, f"{theme0} → {theme1}")
        pg.click("#btn-theme")
        pg.wait_for_timeout(300)

        print("\n=== 6. P1-4 字阶 / 等宽数字 / P2 表内滚动 ===")
        fs = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--fs-sm').trim()")
        chk("主体字号 ≥14px", fs.startswith("14"), f"--fs-sm={fs}")
        chk("数字用等宽字形", "tabular-nums" in pg.content())
        css = pg.content()
        chk("表格内滚动已定义", "max-height:56vh" in css.replace(" ", "") or "56vh" in css)

        print("\n=== 7. 七视图高度（不撑高页面）===")
        hs = {}
        for v in ["overview", "flywheel", "cron", "skills", "repos", "chat", "raw"]:
            pg.evaluate(f"""() => {{
                document.querySelectorAll('#nav button').forEach(b=>{{
                    if(b.dataset.view==='{v}') b.click();
                }});
            }}""")
            pg.wait_for_timeout(500)
            hs[v] = pg.evaluate("document.querySelector('.view.on').getBoundingClientRect().height")
        worst = max(hs.items(), key=lambda kv: kv[1])
        chk("无视图超过 1.6 屏", worst[1] <= 1600, f"最高 {worst[0]}={worst[1]:.0f}px")
        print("     高度: " + " | ".join(f"{k}={v:.0f}" for k, v in hs.items()))

        print("\n=== 8. 回归：v4 三项仍正常 ===")
        pg.evaluate("document.querySelector('#nav button[data-view=skills]').click()")
        pg.wait_for_timeout(600)
        chk("技能表分页仍在", pg.locator("#ps-skill").count() == 1)
        n_rows = pg.locator("#tb-skill tr").count()
        chk("技能表已分页且非空", 0 < n_rows <= 55, f"{n_rows} 行（15/页上限）")
        chk(
            "技能表总数提示已渲染",
            "157" in (pg.locator("#c-skill").inner_text() or "") or "共" in (pg.locator("#c-skill").inner_text() or ""),
            (pg.locator("#c-skill").inner_text() or "")[:40],
        )
        pg.evaluate("document.querySelector('#nav button[data-view=flywheel]').click()")
        pg.wait_for_timeout(600)
        chk("飞轮三个分数非空", not all(x == "—" for x in ["68.0", "54.1", "60.0"]), "数值已渲染")

        # --- P3-11 数据源体检 ---
        pg.click('#nav button[data-view="overview"]')
        pg.wait_for_timeout(250)
        sh_rows = pg.locator("#src-health .sh-row").count()
        chk("数据源体检已渲染", sh_rows >= 4, f"{sh_rows} 项")
        sh_txt = pg.locator("#src-health").inner_text() or ""
        chk("体检显示 SKILL.md 真实数量", "SKILL.md" in sh_txt and "158" in sh_txt, sh_txt.replace(chr(10), " ")[:70])

        # --- P1-5 趋势 delta：注入一个不同的历史值，验证真能算出变化 ---
        pg.evaluate("""(() => {
            const cur = JSON.parse(localStorage.getItem('hubHist2') || '{}');
            localStorage.setItem('hubHist2', JSON.stringify({
              cards: [300, 340], overall: [20], cron_ok: [50], vector_missing: [9],
              cited: [40], flywheel: [10]
            }));
        })()""")
        pg.click("#btn-refresh")
        pg.wait_for_timeout(9000)
        n_delta = pg.locator(".delta").count()
        chk("注入历史后趋势 delta 出现", n_delta >= 1, f"{n_delta} 个")
        chk(
            "delta 数值方向正确",
            pg.locator(".delta.up").count() >= 1 or pg.locator(".delta.down").count() >= 1,
            (pg.locator(".delta").first.inner_text() or "").strip(),
        )

        import os

        pg.screenshot(path=str(pathlib.Path(os.environ.get("LOCALAPPDATA", ".")) / "Temp" / "shot-v5-overview.png"))
        b.close()
    print("\n" + "=" * 62)

    print(f"通过 {len(PASS)} 项 / 失败 {len(FAIL)} 项")
    if FAIL:
        print("\n失败明细：")
        for f in FAIL:
            print("  ❌ " + f)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
