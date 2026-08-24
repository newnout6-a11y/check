# language: Python 3.12+, file: test_dns_and_scan.py, target: Windows 11
import asyncio
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor
import aiohttp

sys_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def resolve_host(host):
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None

async def probe_endpoint(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6), ssl=False, allow_redirects=True) as r:
            text = await r.text(errors="replace")
            return r.status, str(r.url), text, dict(r.headers)
    except Exception:
        return 0, url, "", {}

async def scan_domain(session, domain, sem):
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
    }

    async with sem:
        try:
            # 1. /my-account/
            s, u, html, h = await probe_endpoint(session, f"{base}/my-account/")
            if s > 0:
                if "cf-ray" in h or "cf_clearance" in str(h) or "Just a moment..." in html:
                    res["cf_protected"] = True
                pks = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", html)
                if pks:
                    res["pk_live"] = pks[0]
                if 'woocommerce-register-nonce' in html:
                    res["open_reg"] = True
                    res["features"].append("wc_open_reg")

            # 2. /my-account/add-payment-method/
            s, u, html_pm, h = await probe_endpoint(session, f"{base}/my-account/add-payment-method/")
            if s > 0:
                pks = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", html_pm)
                if pks and not res["pk_live"]:
                    res["pk_live"] = pks[0]
                if 'createAndConfirmSetupIntentNonce' in html_pm:
                    res["wc_upe"] = True
                    res["features"].append("wc_upe")
                if 'add_card_nonce' in html_pm:
                    res["wc_legacy"] = True
                    res["features"].append("wc_legacy")

            # 3. GiveWP / Donations
            for p in ["/donate/", "/donations/", "/give/"]:
                s, u, d_html, h = await probe_endpoint(session, f"{base}{p}")
                if s == 200 and ("give-form" in d_html or "give_stripe" in d_html or "give-donation" in d_html):
                    res["givewp"] = True
                    res["features"].append(f"givewp{p}")
                    pks = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", d_html)
                    if pks and not res["pk_live"]:
                        res["pk_live"] = pks[0]
                    break

            # 4. Checkout
            s, u, c_html, h = await probe_endpoint(session, f"{base}/checkout/")
            if s == 200 and ("woocommerce-checkout" in c_html or "wc-stripe" in c_html):
                res["features"].append("checkout")
                pks = re.findall(r"pk_live_[0-9a-zA-Z]{24,}", c_html)
                if pks and not res["pk_live"]:
                    res["pk_live"] = pks[0]

            if res["features"] or res["pk_live"]:
                return res
        except Exception:
            pass
    return None

def main():
    domains = []
    for fn in ["harvested_domains.txt", "probe_targets.txt"]:
        try:
            with open(fn, encoding="utf-8") as f:
                domains.extend([l.strip() for l in f if l.strip()])
        except Exception:
            pass

    cleaned = []
    for d in domains:
        d = re.sub(r'[^a-z0-9.-]', '', d.strip().lower())
        if d and "." in d and not d.endswith("."):
            cleaned.append(d)
    raw_domains = sorted(list(set(cleaned)))

    print(f"[*] Pre-resolving DNS for {len(raw_domains)} domains...", flush=True)
    live_domains = []
    with ThreadPoolExecutor(max_workers=30) as pool:
        results = pool.map(resolve_host, raw_domains)
        for r in results:
            if r:
                live_domains.append(r)

    print(f"[*] DNS OK on {len(live_domains)} / {len(raw_domains)} domains.", flush=True)

    async def run_scan():
        sem = asyncio.Semaphore(15)
        headers = {
            "User-Agent": sys_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        conn = aiohttp.TCPConnector(ssl=False, limit=30)
        async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
            tasks = [scan_domain(session, d, sem) for d in live_domains]
            res = await asyncio.gather(*tasks)
            valid = [r for r in res if r]

            print(f"\n[+] Active payment surfaces found: {len(valid)}")
            for v in valid:
                pk_disp = v["pk_live"][:25] + "..." if v["pk_live"] else "no_pk"
                cf_tag = "[CF]" if v["cf_protected"] else "[CLEAN]"
                feats = ", ".join(v["features"]) if v["features"] else "none"
                print(f"  {cf_tag:7} {v['domain']:32} | PK: {pk_disp:28} | Feats: {feats}")

            with open("active_surfaces.json", "w", encoding="utf-8") as f:
                json.dump(valid, f, indent=2)

    asyncio.run(run_scan())

if __name__ == "__main__":
    main()
