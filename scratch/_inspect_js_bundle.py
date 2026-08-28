import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_js():
    # Read the script urls from checkout_page.html
    with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
        html = f.read()

    js_files = re.findall(r'(/cdn/shopifycloud/checkout-web/assets/c1/[a-zA-Z0-9._-]+\.js)', html)
    js_files = list(set(js_files))
    print(f"Found {len(js_files)} JS files in checkout assets.")
    
    # Let's download a few key ones: graphql, payment, negotiation, payNow
    key_files = [f for f in js_files if any(k in f.lower() for k in ["graphql", "payment", "negotiat", "paynow", "submit", "card", "vault", "session"])]
    print(f"Key JS files: {key_files}")

    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for jf in key_files[:8]:
            url = f"https://cdn.shopify.com{jf}"
            r = await s.get(url)
            print(f"\n--- {jf} (len {len(r.text)}) ---")
            # Look for mutation, query, fetch, post, endpoint
            mutations = re.findall(r'mutation\s+([a-zA-Z0-9_]+)', r.text)
            print(f"  Mutations: {mutations}")
            endpoints = re.findall(r'["\'](/checkouts/[a-zA-Z0-9/_.-]+)["\']', r.text)
            print(f"  Endpoints: {list(set(endpoints))[:5]}")
            deposit_urls = re.findall(r'https?://[a-zA-Z0-9.-]*(?:shopifycs|shopifyinc)[a-zA-Z0-9./_-]*', r.text)
            print(f"  Vault/Sink URLs: {list(set(deposit_urls))}")

if __name__ == "__main__":
    asyncio.run(inspect_js())
