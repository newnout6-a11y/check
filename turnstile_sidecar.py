# language: Python, file: turnstile_sidecar.py, target: Windows/Linux
"""
Turnstile Local Zero-Cost Headless Sidecar.
Solves Cloudflare Turnstile (non-interactive and managed) locally without external paid APIs or ML models.
Uses patchright with native system Chrome and CDP (Chrome DevTools Protocol).
"""
import asyncio
import os
import shutil
from typing import Optional


CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = shutil.which("chrome") or shutil.which("google-chrome") or "chromium"


async def solve_turnstile_async(
    url: str,
    timeout_sec: float = 15.0,
    headless: bool = True
) -> Optional[str]:
    """
    Navigates to URL, waits for Turnstile widget resolution, and extracts cf-turnstile-response token.
    Supports both non-interactive and managed (checkbox) Turnstile.
    """
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                executable_path=CHROME_PATH,
                headless=headless
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=int(timeout_sec * 1000))
            except Exception:
                pass

            token = None
            max_steps = int(timeout_sec / 0.5)
            for _ in range(max_steps):
                await asyncio.sleep(0.5)
                # Check for hidden response element
                el = await page.query_selector('[name="cf-turnstile-response"]')
                if el:
                    val = await el.get_attribute("value")
                    if val and len(val) > 40:
                        token = val
                        break

                # If interactive challenge is presented inside iframe, click it
                for frame in page.frames:
                    if "challenges.cloudflare.com" in frame.url:
                        try:
                            box = await frame.query_selector('input[type="checkbox"], #challenge-stage')
                            if box:
                                await box.click()
                        except Exception:
                            pass

            await browser.close()
            return token
    except Exception:
        return None


def solve_turnstile(url: str, timeout_sec: float = 15.0, headless: bool = True) -> Optional[str]:
    """Synchronous wrapper for solve_turnstile_async."""
    try:
        return asyncio.run(solve_turnstile_async(url, timeout_sec=timeout_sec, headless=headless))
    except Exception:
        return None