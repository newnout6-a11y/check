# language: Python 3.12+, file: scratch/deep_dorker.py, target: Windows 11
import asyncio
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень проекта при любом cwd

from curl_cffi.requests import AsyncSession

import gate_client as gc
import config

QUERIES = [
    # WooCommerce Stripe Specific Script & Nonce dorks
    '"var wc_stripe_upe_params" "createAndConfirmSetupIntentNonce"',
    '"createAndConfirmSetupIntentNonce" "my-account"',
    '"wc_stripe_params" "add_card_nonce" "my-account"',
    '"wp-content/plugins/woocommerce-gateway-stripe" "my-account"',
    '"wp-content/plugins/woo-stripe-payment" "my-account"',
    '"wp-content/plugins/woocommerce-subscriptions" "add-payment-method"',
    
    # Exact text strings on WooCommerce Stripe Add Payment Method page
    '"Save payment information to my account for future purchases" "add-payment-method"',
    '"Enter your payment details to save your card" "add-payment-method"',
    '"Pay with your credit card via Stripe" "add-payment-method"',
    '"Credit Card (Stripe)" "Add payment method" "Billing address"',
    '"Add a new payment method to your account" "Stripe"',
    '"Add payment method" "woocommerce-register-nonce"',
    '"woocommerce-form-register" "add-payment-method"',
    
    # Country-specific WooCommerce stores with open accounts
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.au',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.uk',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.ca',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.nz',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.us',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.de',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.fr',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.it',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.es',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.nl',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.eu',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.store',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.shop',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.co',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.io',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.club',
    '"/my-account/add-payment-method/" "Credit Card (Stripe)" site:.app',
    
    # Subscriptions & Memberships specific
    '"/my-account/add-payment-method/" "Subscription" "Stripe"',
    '"/my-account/add-payment-method/" "Membership" "Stripe"',
    '"/my-account/add-payment-method/" "Monthly" "Stripe"',
    '"/my-account/add-payment-method/" "Recurring" "Stripe"',
    '"/my-account/add-payment-method/" "Course" "Stripe"',
    '"/my-account/add-payment-method/" "Yoga" "Stripe"',
    '"/my-account/add-payment-method/" "Fitness" "Stripe"',
    '"/my-account/add-payment-method/" "Coffee" "Stripe"',
    '"/my-account/add-payment-method/" "Wine" "Stripe"',
    '"/my-account/add-payment-method/" "Supplements" "Stripe"',
    '"/my-account/add-payment-method/" "Gym" "Stripe"',
    '"/my-account/add-payment-method/" "Box" "Stripe"',
]

EXCLUDE = [
    "wordpress.org", "wordpress.com", "woocommerce.com", "github.com", "stackoverflow.com",
    "google.com", "bing.com", "yahoo.com", "duckduckgo.com", "apple.com", "microsoft.com",
    "stripe.com", "paypal.com", "zoom.us", "amazon.", "youtube.com", "facebook.com", "x.com"
]

def clean_domain(raw_url_or_host: str) -> str:
    try:
        if not raw_url_or_host.startswith("http"):
            raw_url_or_host = "https://" + raw_url_or_host
        p = urllib.parse.urlparse(raw_url_or_host)
        host = p.netloc.lower()
        if ":" in host:
            host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        host = re.sub(r'[^a-z0-9.-]', '', host)
        if any(ex in host for ex in EXCLUDE):
            return ""
        if "." in host and len(host) > 4 and not host.endswith("."):
            return host
    except Exception:
        pass
    return ""

async def query_ddg(session: AsyncSession, q: str) -> list[str]:
    urls = []
    try:
        r = await session.post("https://html.duckduckgo.com/html/", data={"q": q}, timeout=12)
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            matches = re.findall(r'uddg=([^&"\']+)', r.text)
            for m in matches:
                try:
                    u = urllib.parse.unquote(m)
                    if u.startswith("http"):
                        urls.append(u)
                except Exception:
                    pass
    except Exception:
        pass
    return urls

async def query_yahoo(session: AsyncSession, q: str, page: int = 1) -> list[str]:
    urls = []
    try:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
        if page > 1:
            url += f"&b={7 * page + 1}"
        r = await session.get(url, timeout=12)
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            for m in re.finditer(r'/RU=([^/]+)/', r.text):
                try:
                    u = urllib.parse.unquote(m.group(1))
                    if u.startswith("http"):
                        urls.append(u)
                except Exception:
                    pass
    except Exception:
        pass
    return urls


# --- Sprint 3.2: Bing с пагинацией ---

async def query_bing(session: AsyncSession, q: str, page: int = 1) -> list[str]:
    urls = []
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}"
        if page > 1:
            url += f"&first={10 * (page - 1) + 1}"
        r = await session.get(url, timeout=12,
                              headers={"Accept-Language": "en-US,en;q=0.9"})
        if r.status_code == 200 and not gc.looks_like_captcha(r.text):
            blocks = re.findall(r'<li class="b_algo".*?</li>', r.text, re.S)
            for b in blocks:
                m = re.search(r'<h2[^>]*><a[^>]+href="(https?://[^"]+)"', b)
                if m and not any(x in m.group(1) for x in ["bing.com", "microsoft.com", "go.micro"]):
                    urls.append(m.group(1))
    except Exception:
        pass
    return urls


async def harvest(pages: int = 2, limit: int | None = None) -> set:
    """Sprint 3.1/3.2: DDG+Yahoo+Bing × pages страниц; возвращает чистые домены.
    limit — срез списка запросов для смоук-прогонов."""
    queries = QUERIES[:limit] if limit else QUERIES
    all_domains = set()
    # Своя полоса истории: dork-домены уже в db, txt читаем для совместимости
    async with AsyncSession(impersonate=config.pick_impersonate(), verify=False) as session:
        for i, q in enumerate(queries, 1):
            print(f"  [{i:02}/{len(queries)}] Scraping: {q[:55]}...", flush=True)
            found_all: list[str] = []
            for page in range(1, pages + 1):
                links: list[str] = []
                # Пусто или капча → экспоненциальный backoff до 3 попыток
                for attempt in range(3):
                    ddg_links = await query_ddg(session, q)
                    yahoo_links = await query_yahoo(session, q, page)
                    bing_links = await query_bing(session, q, page)
                    links = ddg_links + yahoo_links + bing_links
                    if links:
                        break
                    print(f"       !! empty/captcha suspected — backoff, attempt {attempt + 1}/3", flush=True)
                    await gc.backoff_sleep(attempt)
                found_all.extend(links)

            new_found = 0
            for link in set(found_all):
                cd = clean_domain(link)
                if cd and cd not in all_domains:
                    all_domains.add(cd)
                    new_found += 1
            print(f"       -> +{new_found} new domains | Total unique: {len(all_domains)}", flush=True)
            await gc.polite_delay(1.2, 1.3)
    return all_domains


async def main():
    import domains_store
    domains_store.init_db()
    limit = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            limit = max(1, int(sys.argv[i + 1]))
    print("=" * 80)
    print(f"[*] DEEP DORK HARVESTER v3 — MULTI-QUERY WOOCOMMERCE & STRIPE UPE DISCOVERY{f' [smoke limit={limit}]' if limit else ''}")
    print(f"[*] Total Queries: {limit or len(QUERIES)}")
    print("=" * 80)

    all_domains = await harvest(pages=2, limit=limit)

    added = domains_store.upsert(all_domains, source="dork", priority=3)
    print(f"[+] DB upsert: +{added} new")
    out_path = "data/dork_harvested.txt"
    total = domains_store.export_txt(out_path)
    print("\n" + "=" * 80)
    print(f"[+] {len(all_domains)} clean this run | exported {total} pool domains -> {out_path}")
    s = domains_store.stats()
    print(f"[=] pool: {s['total']} total | sources={s['by_source']} | pending scan={s['pending']}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
