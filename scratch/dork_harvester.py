# language: Python 3.12+, file: scratch/dork_harvester.py, target: Windows 11
import asyncio
import re
import urllib.parse
from curl_cffi import requests
from curl_cffi.requests import AsyncSession

DORKS = [
    '"/my-account/add-payment-method/" "woocommerce"',
    '"/my-account/add-payment-method/" "Stripe"',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)"',
    '"/my-account/add-payment-method/" "saved payment methods"',
    '"/my-account/add-payment-method/" "Billing address"',
    '"/my-account/add-payment-method/" site:.com.au',
    '"/my-account/add-payment-method/" site:.co.uk',
    '"/my-account/add-payment-method/" site:.ca',
    '"/my-account/add-payment-method/" site:.co.nz',
    '"/my-account/add-payment-method/" site:.de',
    '"/my-account/add-payment-method/" site:.it',
    '"/my-account/add-payment-method/" site:.es',
    '"/my-account/add-payment-method/" site:.nl',
    '"/my-account/add-payment-method/" site:.se',
    '"/my-account/add-payment-method/" site:.ch',
    '"/my-account/add-payment-method/" site:.ie',
    '"/my-account/add-payment-method/" site:.us',
    '"/my-account/add-payment-method/" site:.org',
    '"/my-account/add-payment-method/" site:.store',
    '"/my-account/add-payment-method/" site:.shop',
    '"/my-account/add-payment-method/" site:.club',
    '"/my-account/add-payment-method/" site:.fitness',
    '"/my-account/add-payment-method/" site:.academy',
    '"wc_stripe_upe_params" "createAndConfirmSetupIntentNonce"',
    '"wc_stripe_params" "add_card_nonce"',
    '"var wc_stripe_upe_params"',
    '"/my-account/" "Create an account" "add-payment-method"',
    'inurl:add-payment-method "woocommerce-register-nonce"',
]

def parse_ddg_html(html: str) -> list[str]:
    urls = []
    matches = re.findall(r'uddg=([^&"\']+)', html)
    for m in matches:
        try:
            u = urllib.parse.unquote(m)
            if u.startswith("http"):
                urls.append(u)
        except Exception:
            pass
    # Also standard href regex
    hrefs = re.findall(r'href="(https?://[^"]+)"', html)
    for h in hrefs:
        if not any(x in h for x in ["duckduckgo.com", "bing.com", "google.com", "microsoft.com", "yahoo.com"]):
            urls.append(h)
    return list(set(urls))

async def search_dork_ddg(session: AsyncSession, dork: str) -> list[str]:
    try:
        r = await session.post("https://html.duckduckgo.com/html/", data={"q": dork}, timeout=12)
        if r.status_code == 200:
            urls = parse_ddg_html(r.text)
            return urls
    except Exception as e:
        print(f"Error for '{dork}': {e}")
    return []

async def search_dork_yahoo(session: AsyncSession, dork: str) -> list[str]:
    try:
        q = urllib.parse.quote(dork)
        url = f"https://search.yahoo.com/search?p={q}"
        r = await session.get(url, timeout=12)
        if r.status_code == 200:
            raw_links = re.findall(r'href="(https?://[^"]+)"', r.text)
            clean = []
            for l in raw_links:
                if "/RU=" in l:
                    m = re.search(r'/RU=([^/]+)/', l)
                    if m:
                        try:
                            clean.append(urllib.parse.unquote(m.group(1)))
                        except Exception:
                            pass
                elif not any(x in l for x in ["yahoo.com", "yimg.com", "bing.com", "google.com"]):
                    clean.append(l)
            return list(set(clean))
    except Exception as e:
        pass
    return []

async def main():
    print("[*] Launching Dork Search Engine Harvester (DuckDuckGo + Yahoo via Chrome TLS)...")
    all_domains = set()
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for i, d in enumerate(DORKS, 1):
            print(f"  [{i:02}/{len(DORKS)}] Querying: {d[:50]}...", flush=True)
            ddg_urls = await search_dork_ddg(s, d)
            yahoo_urls = await search_dork_yahoo(s, d)
            found = set(ddg_urls + yahoo_urls)
            
            for u in found:
                try:
                    p = urllib.parse.urlparse(u)
                    host = p.netloc.lower()
                    if ":" in host:
                        host = host.split(":")[0]
                    if host.startswith("www."):
                        host = host[4:]
                    host = re.sub(r'[^a-z0-9.-]', '', host)
                    if "." in host and len(host) > 4:
                        all_domains.add(host)
                except Exception:
                    pass
            print(f"       -> Extracted {len(found)} URLs, total unique domains: {len(all_domains)}", flush=True)
            await asyncio.sleep(1.5)
            
    print(f"\n[+] Total unique target domains harvested: {len(all_domains)}")
    out_file = "data/dork_harvested.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        for d in sorted(all_domains):
            f.write(d + "\n")
    print(f"[+] Saved to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
