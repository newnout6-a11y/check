# language: Python 3.12+, file: scratch/deep_dorker.py, target: Windows 11
import asyncio
import re
import urllib.parse
from curl_cffi.requests import AsyncSession

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
        if r.status_code == 200:
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

async def query_yahoo(session: AsyncSession, q: str) -> list[str]:
    urls = []
    try:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
        r = await session.get(url, timeout=12)
        if r.status_code == 200:
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

async def main():
    print("=" * 80)
    print("[*] DEEP DORK HARVESTER v2 — MULTI-QUERY WOOCOMMERCE & STRIPE UPE DISCOVERY")
    print(f"[*] Total Queries: {len(QUERIES)}")
    print("=" * 80)
    
    all_domains = set()
    
    # Load existing harvested domains to merge
    for fn in ["data/harvested_domains.txt", "data/dork_harvested.txt"]:
        try:
            with open(fn, "r", encoding="utf-8") as f:
                for line in f:
                    c = clean_domain(line.strip())
                    if c:
                        all_domains.add(c)
        except Exception:
            pass
            
    print(f"[*] Initial domain pool size: {len(all_domains)}")
    
    async with AsyncSession(impersonate="chrome131", verify=False) as session:
        for i, q in enumerate(QUERIES, 1):
            print(f"  [{i:02}/{len(QUERIES)}] Scraping: {q[:55]}...", flush=True)
            ddg_links = await query_ddg(session, q)
            yahoo_links = await query_yahoo(session, q)
            
            new_found = 0
            for link in ddg_links + yahoo_links:
                cd = clean_domain(link)
                if cd and cd not in all_domains:
                    all_domains.add(cd)
                    new_found += 1
            print(f"       -> +{new_found} new domains | Total unique: {len(all_domains)}", flush=True)
            await asyncio.sleep(1.2)
            
    out_path = "data/harvested_domains.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for d in sorted(all_domains):
            f.write(d + "\n")
            
    print("\n" + "=" * 80)
    print(f"[+] Total clean domains saved to {out_path}: {len(all_domains)}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
