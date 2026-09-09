import asyncio
from patchright.async_api import async_playwright

async def test_patchright():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        page = await browser.new_page()
        page.on("requestfailed", lambda req: print("Request failed:", req.url, req.failure))
        page.on("console", lambda msg: print("Console:", msg.type, msg.text))
        
        print("Navigating to peet.ws non-interactive...")
        await page.goto("https://peet.ws/turnstile-test/non-interactive.html", wait_until="networkidle")
        await asyncio.sleep(3)
        
        inputs = await page.query_selector_all("input")
        print("Inputs found:", len(inputs))
        for inp in inputs:
            name = await inp.get_attribute("name")
            val = await inp.get_attribute("value")
            print(f"Input name='{name}', val_len={len(val) if val else 0}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_patchright())