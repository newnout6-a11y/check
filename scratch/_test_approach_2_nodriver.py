"""
Test Approach 2: Local Zero-Cost Headless Sidecar (nodriver + native Chrome).
Solves Cloudflare Turnstile locally without any paid API keys and without ML.
Uses native Chrome via Chrome DevTools Protocol (CDP).
"""
import asyncio
import time
import nodriver as uc

async def solve_turnstile_with_nodriver(url: str, headless: bool = True, timeout: int = 15):
    print(f"=== Starting Local Headless Sidecar (nodriver) ===")
    print(f"Target URL: {url}")
    t0 = time.perf_counter()
    
    # Launch Chrome directly via nodriver
    browser = await uc.start(
        headless=headless,
        browser_executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        browser_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic"
        ]
    )
    
    try:
        t_launch = (time.perf_counter() - t0) * 1000.0
        print(f"Chrome launched in {t_launch:.1f} ms")
        
        page = await browser.get(url)
        print("Page opened, waiting for Turnstile resolution...")
        
        token = None
        start_wait = time.perf_counter()
        while (time.perf_counter() - start_wait) < timeout:
            await asyncio.sleep(0.5)
            # Query the hidden input field created by Turnstile
            try:
                res = await page.evaluate("""
                    (() => {
                        const el = document.querySelector('[name="cf-turnstile-response"]');
                        return el ? el.value : null;
                    })()
                """)
                if res and len(res) > 20:
                    token = res
                    break
            except Exception as e:
                pass
                
        t_total = (time.perf_counter() - t0) * 1000.0
        if token:
            print(f"\n[SUCCESS] Turnstile solved locally!")
            print(f"Token length: {len(token)}")
            print(f"Token snippet: {token[:30]}...{token[-20:]}")
            print(f"Total time: {t_total:.1f} ms")
            return {
                "success": True,
                "token": token,
                "elapsed_ms": t_total
            }
        else:
            print(f"\n[FAIL] Token not found within {timeout}s")
            return {"success": False, "error": "timeout"}
            
    finally:
        browser.stop()
        print("Browser session closed cleanly.")

if __name__ == "__main__":
    url = "https://peet.ws/turnstile-test/non-interactive.html"
    asyncio.run(solve_turnstile_with_nodriver(url, headless=True))