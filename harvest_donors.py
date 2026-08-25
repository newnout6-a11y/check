# language: Python 3.12+, file: harvest_donors.py, target: Windows 11
import asyncio
import os
import re
from urllib.parse import urlparse
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# Tier 1 (High Yield: Subscriptions, Memberships, LMS, Donations, Core Stripe)
PRIORITY_SLUGS = [
    "woocommerce-subscriptions",
    "paid-memberships-pro",
    "memberpress",
    "give",
    "wp-simple-pay",
    "tutor",
    "lifterlms",
    "learnpress",
    "woocommerce-gateway-stripe",
    "woo-stripe-payment",
    "payment-gateway-stripe-and-woocommerce-integration",
    "accept-stripe-payments",
    "stripe-payments",
    "armember-membership",
    "simple-membership",
    "charitable",
    "forminator",
    "wpforms-lite",
    "fluentform",
    "bookly-responsive-appointment-booking-tool",
    "ameliabooking",
    "latepoint",
]

# Tier 2 (Extended E-Commerce & Forms)
EXTENDED_SLUGS = [
    "woocommerce",
    "woocommerce-payments",
    "easy-digital-downloads",
    "surecart",
    "checkout-plugins-stripe-for-woocommerce",
    "wc-stripe-payment-terminal",
    "stripe-for-woocommerce",
    "members",
    "ultimate-member",
    "wp-members",
    "restrict-content",
    "swpm-stripe-payments",
    "s2member",
    "donorbox-donation-form",
    "seamless-donations",
    "wp-crowdfunding",
    "ignitiondeck",
    "fundraising",
    "donation-thermometer",
    "wp-fundraising-donation",
    "sensei-lms",
    "masterstudy-lms",
    "namaste-lms",
    "salon-booking-system",
    "simply-schedule-appointments",
    "easy-appointments",
    "the-events-calendar",
    "event-tickets",
    "events-manager",
    "tickera-event-ticketing-system",
    "event-espresso-decaf",
    "caldera-forms",
    "ninja-forms",
    "formidable",
    "gravity-forms-stripe",
    "ws-form",
]

ALL_SLUGS = PRIORITY_SLUGS + EXTENDED_SLUGS

EXCLUDE_DOMAINS = {
    "wordpress.org", "wordpress.com", "gravatar.com", "google.com", "gstatic.com",
    "s.w.org", "ps.w.org", "fonts.googleapis.com", "github.com", "pastebin.com",
    "loom.com", "snipboard.io", "ibb.co", "youtube.com", "instagram.com", "facebook.com",
    "tiktok.com", "threads.net", "x.com", "twitter.com", "linkedin.com", "bbpress.org",
    "buddypress.org", "woocommerce.com", "w3.org", "googletagmanager.com", "awesomescreenshot.com",
    "openverse.org", "wp.com", "imgur.com", "gyazo.com", "prnt.sc", "lightshot.com",
    "stripe.com", "paypal.com", "wordfence.com", "cloudflare.com", "automattic.com",
    "schema.org", "w.org", "wpackagist.org", "jsdelivr.net", "cloudflareinsights.com",
    "w3schools.com", "stackoverflow.com", "bitly.com", "tinyurl.com", "microsoft.com",
    "bing.com", "yahoo.com", "apple.com", "amazon.com", "supportally.com", "1drv.ms"
}

DEV_KEYWORDS = ["test.", "staging.", "stage.", "dev.", "demo.", "sandbox.", "localhost", "127.0.0.1"]

TOPIC_RE = re.compile(r'href="(https://wordpress\.org/support/topic/[a-z0-9-]+/)"')
LINK_RE = re.compile(r'href="(https?://[^"]+)"')
PLAIN_URL_RE = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})')

# System Status Report Regexes (WooCommerce logs)
STATUS_SITE_RE = re.compile(r'(?:Site URL|Home URL|WordPress address \(URL\)|Site address \(URL\)|Site URL\s*:\s*|Site:\s*)\s*(https?://[^\s\r\n\'"<>]+)', re.IGNORECASE)
STATUS_STRIPE_LIVE_RE = re.compile(r'(?:Stripe Account|Stripe|Mode):\s*(?:Live|Production)', re.IGNORECASE)
STATUS_SUBS_RE = re.compile(r'(?:Subscriptions|WooCommerce Subscriptions|WC Subscriptions)', re.IGNORECASE)


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), ssl=False) as r:
            if r.status == 200:
                return await r.text(errors="replace")
    except Exception:
        pass
    return ""


async def extract_thread_links(session: aiohttp.ClientSession, slug: str, max_pages: int) -> list:
    topics = []
    for p in range(1, max_pages + 1):
        url = f"https://wordpress.org/support/plugin/{slug}/page/{p}/"
        html = await fetch_text(session, url)
        if html:
            matches = TOPIC_RE.findall(html)
            if not matches:
                break
            topics.extend(matches)
        else:
            break
    return list(set(topics))


def sanitize_host(link_or_host: str) -> str:
    if not link_or_host:
        return ""
    link_or_host = link_or_host.strip().rstrip("/").rstrip(".")
    if not link_or_host.startswith("http"):
        link_or_host = "https://" + link_or_host
    try:
        parsed = urlparse(link_or_host)
        host = parsed.netloc.lower()
        if not host:
            return ""
        if ":" in host:
            host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        host = re.sub(r'[^a-z0-9.-]', '', host)
        if any(host == exc or host.endswith("." + exc) for exc in EXCLUDE_DOMAINS):
            return ""
        if "." in host and len(host) > 4 and not host.endswith("."):
            return host
    except Exception:
        pass
    return ""


async def extract_domains_from_topic(session: aiohttp.ClientSession, topic_url: str, sem: asyncio.Semaphore) -> tuple[set, set]:
    domains = set()
    priority_live_domains = set()
    async with sem:
        html = await fetch_text(session, topic_url)
        if not html:
            return domains, priority_live_domains
        
        # 1. Check for WooCommerce System Status Report
        status_matches = STATUS_SITE_RE.findall(html)
        is_stripe_live = bool(STATUS_STRIPE_LIVE_RE.search(html))
        is_subs = bool(STATUS_SUBS_RE.search(html))
        
        for raw_site in status_matches:
            clean = sanitize_host(raw_site)
            if clean:
                domains.add(clean)
                if is_stripe_live or is_subs:
                    priority_live_domains.add(clean)
        
        # 2. General links and plain URLs in the post
        all_links = LINK_RE.findall(html) + PLAIN_URL_RE.findall(html)
        for link in all_links:
            clean = sanitize_host(link)
            if clean:
                domains.add(clean)
                
    return domains, priority_live_domains


async def main():
    print("=" * 80)
    print("[*] HARVEST DONORS v3 — TARGETED SUBSCRIPTIONS, LMS, GIVEWP & STATUS SCRAPER")
    print(f"[*] Priority Slugs: {len(PRIORITY_SLUGS)} | Extended Slugs: {len(EXTENDED_SLUGS)}")
    print("=" * 80)
    
    # Load existing domains if available to preserve history
    existing_domains = set()
    out_path = os.path.join("data", "harvested_domains.txt")
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                for line in f:
                    c = sanitize_host(line.strip())
                    if c:
                        existing_domains.add(c)
            print(f"[*] Loaded {len(existing_domains)} pre-existing harvested domains.")
        except Exception:
            pass

    headers = {"User-Agent": UA}
    conn = aiohttp.TCPConnector(ssl=False, limit=60)
    async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
        all_topics = []
        print("[*] Gathering forum topic URLs across categories...", flush=True)
        
        # High-priority slugs get up to 10 pages, extended get 4 pages
        for i, slug in enumerate(ALL_SLUGS, 1):
            max_pages = 10 if slug in PRIORITY_SLUGS else 4
            topics = await extract_thread_links(session, slug, max_pages=max_pages)
            if topics:
                print(f"  [{i:02}/{len(ALL_SLUGS)}] {slug:50} -> {len(topics):3} topics", flush=True)
                all_topics.extend(topics)
                
        all_topics = list(set(all_topics))
        print(f"\n[*] Total unique topics collected: {len(all_topics)}", flush=True)
        print("[*] Parsing topics for donor store domains and status reports...", flush=True)
        
        sem = asyncio.Semaphore(40)
        tasks = [extract_domains_from_topic(session, t, sem) for t in all_topics]
        results = await asyncio.gather(*tasks)
        
        unique_domains = set(existing_domains)
        priority_domains = set()
        
        for d_set, p_set in results:
            unique_domains.update(d_set)
            priority_domains.update(p_set)
            
        print(f"\n[+] Total unique candidate domains: {len(unique_domains)}")
        print(f"[+] Priority Live/Subs domains:     {len(priority_domains)}")
        
        os.makedirs("data", exist_ok=True)
        
        # Sort domains: Priority first (excluding staging/dev), then normal clean domains, then staging
        clean_priority = [d for d in priority_domains if not any(k in d for k in DEV_KEYWORDS)]
        clean_others = [d for d in (unique_domains - priority_domains) if not any(k in d for k in DEV_KEYWORDS)]
        dev_domains = [d for d in unique_domains if any(k in d for k in DEV_KEYWORDS)]
        
        final_sorted = sorted(clean_priority) + sorted(clean_others) + sorted(dev_domains)
        with open(out_path, "w", encoding="utf-8") as f:
            for d in final_sorted:
                f.write(d + "\n")
                
        print(f"[+] Successfully saved {len(final_sorted)} domains to {out_path}", flush=True)
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
