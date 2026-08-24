# language: Python 3.12+, file: harvest_donors.py, target: Windows 11
import asyncio
import os
import re
from urllib.parse import urlparse
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# 60+ slugs: E-Commerce, Stripe Gateways, Subscriptions, Memberships, Donations, LMS, Forms, Booking
PLUGIN_SLUGS = [
    # Core E-Commerce & Stripe
    "woocommerce-gateway-stripe",
    "woo-stripe-payment",
    "payment-gateway-stripe-and-woocommerce-integration",
    "pymntpl-paypal-woocommerce",
    "woocommerce-payments",
    "woocommerce",
    "stripe",
    "accept-stripe-payments",
    "wp-stripe-donation",
    "stripe-payments",
    "easy-digital-downloads",
    "surecart",
    "checkout-plugins-stripe-for-woocommerce",
    "wc-stripe-payment-terminal",
    "stripe-for-woocommerce",
    
    # Subscriptions & Memberships
    "woocommerce-subscriptions",
    "paid-memberships-pro",
    "memberpress",
    "members",
    "ultimate-member",
    "wp-members",
    "restrict-content",
    "simple-membership",
    "swpm-stripe-payments",
    "armember-membership",
    "s2member",
    
    # Donations & Crowdfunding
    "give",
    "charitable",
    "wp-simple-pay",
    "donorbox-donation-form",
    "seamless-donations",
    "wp-crowdfunding",
    "ignitiondeck",
    "fundraising",
    "donation-thermometer",
    "wp-fundraising-donation",
    
    # LMS & Online Courses
    "tutor",
    "learnpress",
    "lifterlms",
    "sensei-lms",
    "masterstudy-lms",
    "namaste-lms",
    "academy",
    
    # Booking & Appointments
    "bookly-responsive-appointment-booking-tool",
    "ameliabooking",
    "latepoint",
    "salon-booking-system",
    "simply-schedule-appointments",
    "easy-appointments",
    
    # Events & Ticketing
    "the-events-calendar",
    "event-tickets",
    "events-manager",
    "tickera-event-ticketing-system",
    "event-espresso-decaf",
    
    # Forms & Payment Integrations
    "fluentform",
    "forminator",
    "caldera-forms",
    "ninja-forms",
    "wpforms-lite",
    "formidable",
    "gravity-forms-stripe",
    "ws-form",
]

EXCLUDE_DOMAINS = {
    "wordpress.org", "wordpress.com", "gravatar.com", "google.com", "gstatic.com",
    "s.w.org", "ps.w.org", "fonts.googleapis.com", "github.com", "pastebin.com",
    "loom.com", "snipboard.io", "ibb.co", "youtube.com", "instagram.com", "facebook.com",
    "tiktok.com", "threads.net", "x.com", "twitter.com", "linkedin.com", "bbpress.org",
    "buddypress.org", "woocommerce.com", "w3.org", "googletagmanager.com", "awesomescreenshot.com",
    "openverse.org", "wp.com", "imgur.com", "gyazo.com", "prnt.sc", "lightshot.com",
    "stripe.com", "paypal.com", "wordfence.com", "cloudflare.com", "automattic.com",
    "schema.org", "w.org", "wpackagist.org", "jsdelivr.net", "cloudflareinsights.com",
    "w3schools.com", "stackoverflow.com", "bitly.com", "tinyurl.com"
}

TOPIC_RE = re.compile(r'href="(https://wordpress\.org/support/topic/[a-z0-9-]+/)"')
LINK_RE = re.compile(r'href="(https?://[^"]+)"')
PLAIN_URL_RE = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})')

# System Status Report Regexes (WooCommerce logs)
STATUS_SITE_RE = re.compile(r'(?:Site URL|Home URL|WordPress address \(URL\)|Site address \(URL\)):\s*(https?://[^\s\r\n]+)', re.IGNORECASE)
STATUS_STRIPE_LIVE_RE = re.compile(r'(?:Stripe Account|Stripe|Mode):\s*(?:Live|Production)', re.IGNORECASE)


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), ssl=False) as r:
            if r.status == 200:
                return await r.text(errors="replace")
    except Exception:
        pass
    return ""


async def extract_thread_links(session: aiohttp.ClientSession, slug: str, max_pages: int = 8) -> list:
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
        
        for raw_site in status_matches:
            clean = sanitize_host(raw_site)
            if clean:
                domains.add(clean)
                if is_stripe_live:
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
    print("[*] HARVEST DONORS v2 — MASS WORDPRESS FORUMS & STATUS REPORTS SCRAPER")
    print(f"[*] Total Plugin Slugs: {len(PLUGIN_SLUGS)}")
    print("=" * 80)
    
    headers = {"User-Agent": UA}
    conn = aiohttp.TCPConnector(ssl=False, limit=50)
    async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
        all_topics = []
        print("[*] Gathering forum topic URLs across categories...", flush=True)
        
        for i, slug in enumerate(PLUGIN_SLUGS, 1):
            topics = await extract_thread_links(session, slug, max_pages=8)
            if topics:
                print(f"  [{i:02}/{len(PLUGIN_SLUGS)}] {slug:50} -> {len(topics):3} topics", flush=True)
                all_topics.extend(topics)
                
        all_topics = list(set(all_topics))
        print(f"\n[*] Total unique topics collected: {len(all_topics)}", flush=True)
        print("[*] Parsing topics for donor store domains and status reports...", flush=True)
        
        sem = asyncio.Semaphore(35)
        tasks = [extract_domains_from_topic(session, t, sem) for t in all_topics]
        results = await asyncio.gather(*tasks)
        
        unique_domains = set()
        priority_domains = set()
        
        for d_set, p_set in results:
            unique_domains.update(d_set)
            priority_domains.update(p_set)
            
        print(f"\n[+] Total unique candidate domains: {len(unique_domains)}")
        print(f"[+] Priority Live Status domains:   {len(priority_domains)}")
        
        os.makedirs("data", exist_ok=True)
        out_path = os.path.join("data", "harvested_domains.txt")
        
        # Write priority first, then others
        sorted_domains = sorted(list(priority_domains)) + sorted(list(unique_domains - priority_domains))
        with open(out_path, "w", encoding="utf-8") as f:
            for d in sorted_domains:
                f.write(d + "\n")
                
        print(f"[+] Saved to {out_path}", flush=True)
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
