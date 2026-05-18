import asyncio
from playwright.async_api import async_playwright

DEMO_PAUSED_ID = "00000000-0000-0000-0000-000000000202"
DEMO_APPROVED_ID = "00000000-0000-0000-0000-000000000101"
OUT = "demo"

async def screenshot(page, url, path, wait_ms=1500):
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(wait_ms)
    await page.screenshot(path=path, full_page=True)
    print(f"  saved {path}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        print("Taking dashboard screenshot...")
        await screenshot(page, "http://127.0.0.1:8001/dashboard",
                         f"{OUT}/dashboard.png")

        print("Taking human review screen screenshot...")
        await screenshot(page, f"http://127.0.0.1:8001/review/{DEMO_PAUSED_ID}",
                         f"{OUT}/review-screen.png")

        print("Taking audit trail screenshot...")
        await screenshot(page, f"http://127.0.0.1:8001/audit/{DEMO_APPROVED_ID}",
                         f"{OUT}/audit-trail.png")

        await browser.close()
        print("Done.")

asyncio.run(main())
