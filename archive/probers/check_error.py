# language: Python 3.12+, file: check_error.py, target: Windows 11
import asyncio
import re
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


async def main():
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        async with s.get("https://www.thetrendywhippet.co.uk/my-account/") as r:
            html = await r.text()
        m = re.search(r'woocommerce-register-nonce["\']\s*value=["\']([a-f0-9]+)["\']', html)
        if not m:
            print("No nonce")
            return
        nonce = m.group(1)
        body = {
            "email": "testuser9918237@gmail.com",
            "password": "Password!1234981",
            "woocommerce-register-nonce": nonce,
            "_wp_http_referer": "/my-account/",
            "register": "Register"
        }
        async with s.post("https://www.thetrendywhippet.co.uk/my-account/", data=body) as r:
            post_html = await r.text()
            
        print("Status:", r.status)
        print("URL:", r.url)
        # Search for error messages or notices
        for pattern in [
            r'<ul class="woocommerce-error"[^>]*>(.*?)</ul>',
            r'<div class="woocommerce-notices-wrapper">(.*?)</div>',
            r'<div class="woocommerce-error"[^>]*>(.*?)</div>',
            r'alert-danger[^>]*>(.*?)</div>',
        ]:
            matches = re.findall(pattern, post_html, re.S)
            if matches:
                clean = re.sub(r'<[^>]+>', ' ', matches[0]).strip()
                print("Notice found:", clean)


if __name__ == "__main__":
    asyncio.run(main())
