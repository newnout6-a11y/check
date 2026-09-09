import asyncio
import time
from patchright.async_api import async_playwright

async def test_managed_turnstile():
    print("=== Testing Managed Turnstile Solver ===")
    t0 = time.perf_counter()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to peet.ws managed.html...")
        await page.goto("https://peet.ws/turnstile-test/managed.html", wait_until="networkidle")
        
        # Look for iframe or checkbox if present
        token = None
        for attempt in range(20):
            await asyncio.sleep(0.5)
            # Try getting input value
            el = await page.query_selector('[name="cf-turnstile-response"]')
            if el:
                val = await el.get_attribute("value")
                if val and len(val) > 50:
                    token = val
                    break
            
            # If not yet solved, check if there is an iframe with checkbox to click
            frames = page.frames
            for f in frames:
                if "cloudflare" in f.url or "challenges" in f.url:
                    try:
                        box = await f.query_selector('input[type="checkbox"], body, #challenge-stage')
                        if box:
                            await box.click()
                    except Exception:
                        pass
                        
        elapsed = (time.perf_counter() - t0) * 1000.0
        if token:
            print(f"[MANAGED SUCCESS] Token generated: len={len(token)}, time={elapsed:.1f} ms")
            print(f"Token snippet: {token[:35]}...{token[-25:]}")
        else:
            print(f"[MANAGED TIMEOUT] after {elapsed:.1f} ms")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_managed_turnstile())