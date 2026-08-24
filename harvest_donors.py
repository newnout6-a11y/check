# language: Python 3.12+, file: harvest_donors.py, target: Windows 11
import asyncio
import re
from urllib.parse import urlparse
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

PLUGIN_SLUGS = [
    "woocommerce-gateway-stripe",
    "woo-stripe-payment",
    "woocommerce-subscriptions",
    "payment-gateway-stripe-and-woocommerce-integration",
    "paid-memberships-pro",
    "give",
    "charitable",
    "wp-simple-pay",
    "tutor",
    "learnpress",
    "lifterlms",
    "members",
    "ultimate-member",
    "wp-members",
]

EXCLUDE_DOMAINS = {
    "wordpress.org", "wordpress.com", "gravatar.com", "google.com", "gstatic.com",
    "s.w.org", "ps.w.org", "fonts.googleapis.com", "github.com", "pastebin.com",
    "loom.com", "snipboard.io", "ibb.co", "youtube.com", "instagram.com", "facebook.com",
    "tiktok.com", "threads.net", "x.com", "twitter.com", "linkedin.com", "bbpress.org",
    "buddypress.org", "woocommerce.com", "w3.org", "googletagmanager.com", "awesomescreenshot.com",
    "openverse.org", "wp.com", "imgur.com", "gyazo.com", "prnt.sc", "lightshot.com",
    "stripe.com", "paypal.com", "wordfence.com", "cloudflare.com", "automattic.com"
}

TOPIC_RE = re.compile(r'href="(https://wordpress\.org/support/topic/[a-z0-9-]+/)"')
LINK_RE = re.compile(r'href="(https?://[^"]+)"')
PLAIN_URL_RE = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})')


async def fetch_text(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as r:
            if r.status == 200:
                return await r.text()
    except Exception:
        pass
    return ""


async def extract_thread_links(session, slug, max_pages=3):
    topics = []
    for p in range(1, max_pages + 1):
        url = f"https://wordpress.org/support/plugin/{slug}/page/{p}/"
        html = await fetch_text(session, url)
        if html:
            matches = TOPIC_RE.findall(html)
            topics.extend(matches)
    return list(set(topics))


async def extract_domains_from_topic(session, topic_url, sem):
    domains = set()
    async with sem:
        html = await fetch_text(session, topic_url)
        if not html:
            return domains
        
        # Look for links and plaintext URLs in the forum topic body
        for link in LINK_RE.findall(html) + PLAIN_URL_RE.findall(html):
            if not link.startswith("http"):
                link = "https://" + link
            try:
                parsed = urlparse(link)
                host = parsed.netloc.lower()
                if not host:
                    continue
                if ":" in host:
                    host = host.split(":")[0]
                if host.startswith("www."):
                    host = host[4:]
                if any(host == exc or host.endswith("." + exc) for exc in EXCLUDE_DOMAINS):
                    continue
                if "." in host and len(host) > 4:
                    domains.add(host)
            except Exception:
                continue
    return domains


async def main():
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        print("[*] Fetching topics across membership, LMS, and Stripe plugins...", flush=True)
        all_topics = []
        for slug in PLUGIN_SLUGS:
            topics = await extract_thread_links(session, slug, max_pages=3)
            print(f"  {slug}: {len(topics)} topics", flush=True)
            all_topics.extend(topics)
        
        all_topics = list(set(all_topics))
        print(f"[*] Total unique topics: {len(all_topics)}", flush=True)
        
        sem = asyncio.Semaphore(20)
        tasks = [extract_domains_from_topic(session, t, sem) for t in all_topics]
        results = await asyncio.gather(*tasks)
        
        unique_domains = set()
        for r in results:
            unique_domains.update(r)
            
        print(f"[*] Total unique candidate domains harvested: {len(unique_domains)}", flush=True)
        
        with open("harvested_domains.txt", "w", encoding="utf-8") as f:
            for d in sorted(unique_domains):
                f.write(d + "\n")
        print("[+] Saved to harvested_domains.txt", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
