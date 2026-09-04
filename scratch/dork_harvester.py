# language: Python 3.12+, file: scratch/dork_harvester.py, target: Windows 11
import asyncio
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень проекта при любом cwd

from curl_cffi import requests
from curl_cffi.requests import AsyncSession

import gate_client as gc
import config

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
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            urls = parse_ddg_html(r.text)
            return urls
    except Exception as e:
        print(f"Error for '{dork}': {e}")
    return []

async def search_dork_yahoo(session: AsyncSession, dork: str, page: int = 1) -> list[str]:
    try:
        q = urllib.parse.quote(dork)
        url = f"https://search.yahoo.com/search?p={q}"
        if page > 1:
            url += f"&b={7 * page + 1}"
        r = await session.get(url, timeout=12)
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
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


# --- Sprint 3.2: движки Bing и AOL + пагинация ---

async def search_dork_bing(session: AsyncSession, dork: str, page: int = 1) -> list[str]:
    try:
        q = urllib.parse.quote(dork)
        url = f"https://www.bing.com/search?q={q}"
        if page > 1:
            url += f"&first={10 * (page - 1) + 1}"
        r = await session.get(url, timeout=12,
                              headers={"Accept-Language": "en-US,en;q=0.9"})
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            # li.b_algo h2 a — органика Bing
            blocks = re.findall(r'<li class="b_algo".*?</li>', r.text, re.S)
            urls = []
            for b in blocks:
                m = re.search(r'<h2[^>]*><a[^>]+href="(https?://[^"]+)"', b)
                if m and not any(x in m.group(1) for x in ["bing.com", "microsoft.com", "go.micro"]):
                    urls.append(m.group(1))
            return list(set(urls))
    except Exception as e:
        pass
    return []


async def search_dork_aol(session: AsyncSession, dork: str, page: int = 1) -> list[str]:
    try:
        q = urllib.parse.quote(dork)
        url = f"https://search.aol.com/aol/search?q={q}"
        if page > 1:
            url += f"&b={10 * (page - 1) + 1}"
        r = await session.get(url, timeout=12)
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            clean = []
            for m in re.finditer(r'/RU=([^/]+)/', r.text):
                try:
                    u = urllib.parse.unquote(m.group(1))
                    if u.startswith("http") and "aol.com" not in u:
                        clean.append(u)
                except Exception:
                    pass
            return list(set(clean))
    except Exception as e:
        pass
    return []

async def harvest(pages: int = 2, limit: int | None = None) -> set:
    """Sprint 3.1/3.2: 4 движка × pages страниц на дорк; возвращает домены.
    limit — срез списка дорков для смоук-прогонов."""
    dorks = DORKS[:limit] if limit else DORKS
    all_domains = set()
    async with AsyncSession(impersonate=config.pick_impersonate(), verify=False) as s:
        for i, d in enumerate(dorks, 1):
            print(f"  [{i:02}/{len(dorks)}] Querying: {d[:50]}...", flush=True)
            found_all: list[str] = []
            for page in range(1, pages + 1):
                found_page: list[str] = []
                # Пусто или капча → экспоненциальный backoff до 3 попыток
                for attempt in range(3):
                    ddg_urls = await search_dork_ddg(s, d)
                    yahoo_urls = await search_dork_yahoo(s, d, page)
                    bing_urls = await search_dork_bing(s, d, page)
                    aol_urls = await search_dork_aol(s, d, page)
                    found_page = ddg_urls + yahoo_urls + bing_urls + aol_urls
                    if found_page:
                        break
                    print(f"       !! empty/captcha suspected — backoff, attempt {attempt + 1}/3", flush=True)
                    await gc.backoff_sleep(attempt)
                found_all.extend(found_page)
                if page < pages and not found_page:
                    break  # вторая страница пуста без первой — дальше не идём
            found = set(found_all)

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
            print(f"       -> Extracted {len(found)} URLs (page x{pages}), total unique domains: {len(all_domains)}", flush=True)
            await gc.polite_delay(1.5, 1.0)
    return all_domains


async def main():
    import domains_store
    domains_store.init_db()
    limit = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            limit = max(1, int(sys.argv[i + 1]))
    print(f"[*] Launching Dork Search Engine Harvester v2 (DDG+Yahoo+Bing+AOL, paginated){f', limit={limit}' if limit else ''}...")
    all_domains = await harvest(pages=2, limit=limit)

    print(f"\n[+] Total unique target domains harvested: {len(all_domains)}")
    added = domains_store.upsert(all_domains, source="dork", priority=3)
    print(f"[+] DB upsert: +{added} new")
    out_file = "data/dork_harvested.txt"
    total = domains_store.export_txt(out_file)
    print(f"[+] exported {total} pool domains -> {out_file}")
    s = domains_store.stats()
    print(f"[=] pool: {s['total']} total | sources={s['by_source']} | pending scan={s['pending']}")

if __name__ == "__main__":
    asyncio.run(main())
