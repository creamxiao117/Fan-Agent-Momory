# @version V1.0 / 2026-09-10 / Hermes / Dashboard pre-commit visual verifier
"""verify_dashboard.py - Dashboard 视觉自查工具.

每项修改后必须运行:
  python verify_dashboard.py --html work/dashboard/index-v3.html

如果 FAIL, 必须修复后再 commit.
"""

import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright


def check(check_name, condition, detail=""):
    """单条检查."""
    sym = "[OK]" if condition else "[FAIL]"
    print(f"  {sym} {check_name}: {detail}")
    return condition


def run_checks(html_path):
    """运行 4 类检查: structure / rendering / interaction / data."""
    results = []
    url = html_path.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(url)
        page.wait_for_timeout(500)

        print("\n=== 1. STRUCTURE (DOM 节点) ===")
        results.append(check("panel-main exists", page.locator("#panel-main").count() == 1))
        results.append(check("5 nav-item exists", page.locator(".nav-item").count() == 5))
        # count hero cards inside panel-main only
        hero_cards = page.evaluate("Array.from(document.querySelectorAll('#panel-main .grid.hero > .card')).length")
        results.append(check("hero card exists (4 in panel-main)", hero_cards == 4, f"count={hero_cards}"))

        print("\n=== 2. RENDERING (visible / display) ===")
        for tab in ["main", "flywheel", "skillhub", "platforms", "hermes"]:
            page.click(f'.nav-item[data-tab="{tab}"]')
            page.wait_for_timeout(200)
            active_panels = page.locator(".panel.active").count()
            results.append(
                check(f"tab={tab} shows exactly 1 active panel", active_panels == 1, f"count={active_panels}")
            )

        print("\n=== 3. INTERACTION (点击/输入测试) ===")
        page.click('.nav-item[data-tab="main"]')
        page.wait_for_timeout(200)
        hero_h = page.evaluate("document.querySelector('#panel-main .grid.hero .card')?.offsetHeight || 0")
        results.append(check("hero card visible height > 50px", hero_h > 50, f"height={hero_h}px"))
        # main tab 3 subtabs (新增)
        subtabs = page.locator("#main-subtabs .subtab").count()
        results.append(check("main tab has 3 subtabs", subtabs == 3, f"count={subtabs}"))
        # subtab 切换
        for sub in ["sys", "cron", "sync"]:
            page.click(f'.subtab[data-subtab="{sub}"]')
            page.wait_for_timeout(150)
            active_sub = page.locator(f'.subtab-content[data-sub="{sub}"]').count()
            results.append(check(f"subtab={sub} shows 1 active", active_sub == 1, f"count={active_sub}"))
        # chat
        page.click('.nav-item[data-tab="hermes"]')
        page.wait_for_timeout(200)
        page.fill("#chat-msg", "test message")
        page.click(".chat-input .btn-primary")
        page.wait_for_timeout(500)
        chat_count = page.locator(".chat-msg").count()
        results.append(check("chat: sendChat produces messages", chat_count >= 2, f"msgs={chat_count}"))
        # nav badge
        for tab in ["main", "flywheel", "platforms"]:
            badge = page.evaluate(f"document.getElementById('nav-badge-{tab}')?.textContent || ''")
            results.append(check(f"nav-badge-{tab} populated", badge and badge.strip() != "...", f"value='{badge}'"))

        print("\n=== 4. DATA (textContent 非空) ===")
        page.click('.nav-item[data-tab="main"]')
        page.wait_for_timeout(200)
        health = page.evaluate("document.getElementById('m-health')?.textContent || ''")
        results.append(check("main.health has data", "/" in health, f"value='{health}'"))
        # cron table has rows
        page.click('.subtab[data-subtab="cron"]')
        page.wait_for_timeout(200)
        cron_rows = page.locator("#tbl-cron tr").count()
        results.append(check("cron table has 7 rows", cron_rows == 7, f"rows={cron_rows}"))
        # flywheel overall
        page.click('.nav-item[data-tab="flywheel"]')
        page.wait_for_timeout(200)
        overall = page.evaluate("document.getElementById('h-overall')?.textContent || ''")
        results.append(check("flywheel.overall has data", overall != "--" and overall != "", f"value='{overall}'"))
        # skillhub cards
        page.click('.nav-item[data-tab="skillhub"]')
        page.wait_for_timeout(200)
        skill_count = page.locator(".skill-card").count()
        results.append(check("skillhub: 19 skill cards rendered", skill_count == 19, f"count={skill_count}"))

        print("\n=== 5. NO JS ERRORS ===")
        results.append(check("no pageerror events", len(console_errors) == 0, f"errors={console_errors[:2]}"))

        browser.close()

    print(f"\n{'=' * 50}")
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"[ALL PASS] {passed}/{total} checks passed")
        return 0
    else:
        print(f"[FAIL] {passed}/{total} checks passed")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Dashboard pre-commit visual verifier")
    parser.add_argument("--html", required=True, help="Path to dashboard HTML file")
    args = parser.parse_args()
    html_path = pathlib.Path(args.html)
    if not html_path.exists():
        print(f"Error: {html_path} not found")
        sys.exit(2)
    sys.exit(run_checks(html_path))


if __name__ == "__main__":
    main()
