# language: Python 3.12+, file: advanced_gate_scanner.py, target: Windows 11
import asyncio
import json
import re
import random
import string
from urllib.parse import urlparse
import aiohttp

sys_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

COMMON_PATHS = [
    "/my-account/",
    "/my-account/add-payment-method/",
    "/donations/",
    "/donate/",
    "/checkout/",
    "/give/",
    "/support-us/",
    "/contribution/",
]

def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

async def probe_url(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), ssl=False, allow_redirects=True) as r:
            text = await r.text(errors="replace")
            return r.status, str(r.url), text, dict(r.headers)
    except BaseException:
        return 0, url, "", {}

async def test_domain_surfaces(session, domain, sem):
    try:
        domain = domain.strip().lower()
        if not domain or "." not in domain:
            return None
        # sanitize domain
        domain = re.sub(r'[^a-z0-9.-]', '', domain)
        if not domain or "." not in domain:
            return None

        base = f"https://{domain}"
        res = {
            "domain": domain,
            "base": base,
            "pk_live": None,
            "features": [],
            "open_reg": False,
            "givewp": False,
            "wc_upe": False,
            "wc_legacy": False,
            "cf_protected": False,
            "endpoints": []
        }

        async with sem:
            # 1. Probe /my-account/
            status, final_url, html, headers = await probe_url(session, f"{base}/my-account/")
            if "cf-ray" in headers or "cf_clearance" in str(headers) or "Just a moment..." in html:
                res["cf_protected"] = True

            pk_matches = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", html)
            if pk_matches:
                res["pk_live"] = pk_matches[0]

            # Check open registration form
            reg_nonce = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
            if reg_nonce:
                res["open_reg"] = True
                res["features"].append("wc_open_reg")

            # 2. Probe /my-account/add-payment-method/
            status_pm, final_pm_url, html_pm, headers_pm = await probe_url(session, f"{base}/my-account/add-payment-method/")
            pk_pm = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", html_pm)
            if pk_pm and not res["pk_live"]:
                res["pk_live"] = pk_pm[0]

            upe_nonce = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', html_pm)
            if upe_nonce:
                res["wc_upe"] = True
                res["features"].append("wc_upe_setup_intent")

            legacy_nonce = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', html_pm)
            if legacy_nonce:
                res["wc_legacy"] = True
                res["features"].append("wc_legacy_setup_intent")

            # 3. Probe GiveWP / Donation endpoints
            for dpath in ["/donate/", "/donations/", "/give/"]:
                d_status, d_url, d_html, d_hdr = await probe_url(session, f"{base}{dpath}")
                if d_status == 200 and ("give-form" in d_html or "give_stripe" in d_html or "give-donation" in d_html):
                    res["givewp"] = True
                    res["features"].append(f"givewp_at_{dpath}")
                    d_pk = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", d_html)
                    if d_pk and not res["pk_live"]:
                        res["pk_live"] = d_pk[0]
                    break

            # 4. Probe /checkout/ for guest checkout
            c_status, c_url, c_html, c_hdr = await probe_url(session, f"{base}/checkout/")
            if c_status == 200 and ("woocommerce-checkout" in c_html or "wc-stripe" in c_html):
                res["features"].append("wc_checkout_active")
                c_pk = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", c_html)
                if c_pk and not res["pk_live"]:
                    res["pk_live"] = c_pk[0]

            if res["features"] or res["pk_live"]:
                return res
            return None
    except BaseException:
        return None

async def main():
    domains = []
    for fn in ["harvested_domains.txt", "probe_targets.txt"]:
        try:
            with open(fn, encoding="utf-8") as f:
                domains.extend([l.strip() for l in f if l.strip()])
        except Exception:
            pass

    # sanitize
    cleaned = []
    for d in domains:
        d = re.sub(r'[^a-z0-9.-]', '', d.strip().lower())
        if d and "." in d and not d.endswith("."):
            cleaned.append(d)
    domains = sorted(list(set(cleaned)))
    print(f"[*] Deep scanning {len(domains)} targets for live gates, GiveWP, and WooCommerce auth vectors...", flush=True)

    sem = asyncio.Semaphore(20)
    headers = {
        "User-Agent": sys_ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    conn = aiohttp.TCPConnector(ssl=False, limit=50)
    async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
        tasks = [test_domain_surfaces(session, d, sem) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    valid = [r for r in results if isinstance(r, dict) and r is not None]
    print(f"\n[+] Found {len(valid)} active target surfaces:")
    for v in valid:
        pk_disp = v["pk_live"][:25] + "..." if v["pk_live"] else "no_pk_scraped"
        cf_tag = "[CF]" if v["cf_protected"] else "[CLEAN]"
        feats = ", ".join(v["features"]) if v["features"] else "none"
        print(f"  {cf_tag:7} {v['domain']:32} | PK: {pk_disp:28} | Feats: {feats}")

    with open("active_surfaces.json", "w", encoding="utf-8") as f:
        json.dump(valid, f, indent=2)
    print(f"\n[+] Saved to active_surfaces.json", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
