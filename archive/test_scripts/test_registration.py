# language: Python 3.12+, file: test_registration.py, target: Windows 11
import asyncio
import random
import re
import string
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))


async def test_reg_thetrendywhippet():
    base = "https://www.thetrendywhippet.co.uk"
    url = f"{base}/my-account/"
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar) as s:
        async with s.get(url, ssl=False) as r:
            html = await r.text()
        
        m_nonce = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
        nonce = m_nonce.group(1) if m_nonce else ""
        print(f"[*] thetrendywhippet nonce: {nonce}")
        
        uname = rand_str(10)
        email = f"{uname}@mailnesia.com"
        pwd = f"SecP@{rand_str(8)}!19"
        
        body = {
            "email": email,
            "password": pwd,
            "woocommerce-register-nonce": nonce,
            "_wp_http_referer": "/my-account/",
            "register": "Register"
        }
        
        async with s.post(url, data=body, ssl=False, headers={"Origin": base, "Referer": url}) as r:
            resp = await r.text()
            print(f"[*] POST status: {r.status}, url: {r.url}")
            
        cookies = {c.key: c.value for c in s.cookie_jar}
        print(f"[*] Cookies: {list(cookies.keys())}")
        logged_in = any("wordpress_logged_in" in k for k in cookies)
        print(f"[*] Logged in: {logged_in}")
        
        if logged_in:
            add_pm = f"{base}/my-account/add-payment-method/"
            async with s.get(add_pm, ssl=False) as r:
                pm_html = await r.text()
                print(f"[*] add-payment-method status: {r.status}, len: {len(pm_html)}")
                m_upe = re.search(r"var wc_stripe_upe_params = (\{.*?\});\s*</script>", pm_html, re.S)
                if m_upe:
                    print(f"[+] Found wc_stripe_upe_params: {m_upe.group(1)[:150]}...")


async def test_reg_lifterlms():
    base = "https://lifterlms.com"
    url = f"{base}/my-account/"
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar) as s:
        async with s.get(url, ssl=False) as r:
            html = await r.text()
        
        m_nonce = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
        nonce = m_nonce.group(1) if m_nonce else ""
        print(f"\n[*] lifterlms nonce: {nonce}")
        
        uname = rand_str(10)
        email = f"{uname}@mailnesia.com"
        
        body = {
            "email": email,
            "woocommerce-register-nonce": nonce,
            "_wp_http_referer": "/my-account/",
            "register": "Register"
        }
        
        async with s.post(url, data=body, ssl=False, headers={"Origin": base, "Referer": url}) as r:
            resp = await r.text()
            print(f"[*] POST status: {r.status}, url: {r.url}")
            
        cookies = {c.key: c.value for c in s.cookie_jar}
        print(f"[*] Cookies: {list(cookies.keys())}")
        logged_in = any("wordpress_logged_in" in k for k in cookies)
        print(f"[*] Logged in: {logged_in}")
        
        if logged_in:
            add_pm = f"{base}/my-account/add-payment-method/"
            async with s.get(add_pm, ssl=False) as r:
                pm_html = await r.text()
                print(f"[*] add-payment-method status: {r.status}, len: {len(pm_html)}")
                m_upe = re.search(r"var wc_stripe_upe_params = (\{.*?\});\s*</script>", pm_html, re.S)
                if m_upe:
                    print(f"[+] Found wc_stripe_upe_params: {m_upe.group(1)[:150]}...")


async def main():
    await test_reg_thetrendywhippet()
    await test_reg_lifterlms()


if __name__ == "__main__":
    asyncio.run(main())
