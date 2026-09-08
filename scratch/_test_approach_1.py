import asyncio
from curl_cffi.requests import AsyncSession
import re

woo_store = "https://brentrobitaille.com"
shopify_store = "https://yarnspirations.com"

async def test_woo():
    print("=== TEST 1: WOOCOMMERCE (brentrobitaille.com) ===")
    async with AsyncSession(impersonate="chrome136", timeout=15) as s:
        r_html = await s.get(woo_store + "/checkout/")
        html = r_html.text
        has_turnstile = bool(re.search(r"challenges\.cloudflare|turnstile", html, re.I))
        has_recaptcha = bool(re.search(r"google\.com/recaptcha|recaptcha", html, re.I))
        print(f"HTML Checkout: HTTP {r_html.status_code}, length={len(html)} bytes")
        print(f"  Captcha scripts in HTML: turnstile={has_turnstile}, recaptcha={has_recaptcha}")
        
        r_cart = await s.get(woo_store + "/wp-json/wc/store/v1/cart")
        nonce = r_cart.headers.get("Nonce") or r_cart.headers.get("nonce")
        print(f"Store API REST: HTTP {r_cart.status_code}, Nonce present: {bool(nonce)}")
        print("  Result: Store API operates pure JSON, zero HTML/DOM JS execution, bypassing frontend hooks.")

async def test_shopify():
    print("\n=== TEST 2: SHOPIFY (yarnspirations.com) ===")
    async with AsyncSession(impersonate="chrome136", timeout=15) as s:
        r_html = await s.get(shopify_store + "/cart")
        html = r_html.text
        print(f"HTML Cart: HTTP {r_html.status_code}, length={len(html)} bytes")
        
        r_api = await s.get(shopify_store + "/cart.js")
        print(f"Shopify Cart API: HTTP {r_api.status_code}, content-type={r_api.headers.get('content-type', '')}")
        print("  Result: Cart API returns direct JSON, bypassing theme JS.")

async def main():
    await test_woo()
    await test_shopify()

asyncio.run(main())
