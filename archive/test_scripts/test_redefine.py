# language: Python 3.12+, file: test_redefine.py, target: Windows 11
import asyncio
import re
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


async def main():
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar) as s:
        url = "https://redefinesolutions.ca/my-account/add-payment-method/"
        async with s.get(url, ssl=False) as r:
            html = await r.text()
        m = re.search(r'woocommerce-register-nonce["\']\s*value=["\']([a-f0-9]+)["\']', html)
        nonce = m.group(1) if m else ""
        print("Nonce:", nonce)
        body = {
            "username": "usr7721948",
            "email": "usr7721948@mailnesia.com",
            "password": "Password!99218",
            "woocommerce-register-nonce": nonce,
            "_wp_http_referer": "/my-account/add-payment-method/",
            "register": "Register"
        }
        async with s.post(url, data=body, ssl=False, headers={"Origin": "https://redefinesolutions.ca", "Referer": url}) as r:
            print("Status:", r.status, "Final URL:", r.url)
        cookies = [c.key for c in s.cookie_jar]
        print("Cookies:", cookies)
        logged_in = any("wordpress_logged_in" in c for c in cookies)
        print("Logged in:", logged_in)


if __name__ == "__main__":
    asyncio.run(main())
