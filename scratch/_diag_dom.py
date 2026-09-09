import asyncio
import nodriver as uc

async def diag():
    browser = await uc.start(
        headless=True,
        browser_executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    try:
        page = await browser.get("https://peet.ws/turnstile-test/non-interactive.html")
        await asyncio.sleep(5)
        html = await page.evaluate("document.body.innerHTML")
        print("DOM length:", len(html))
        print("DOM content:\n", html[:1000])
    finally:
        browser.stop()

if __name__ == "__main__":
    asyncio.run(diag())