import asyncio
import re
from curl_cffi.requests import AsyncSession

async def find_graphql_endpoint():
    with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
        html = f.read()

    js_files = re.findall(r'(/cdn/shopifycloud/checkout-web/assets/c1/[a-zA-Z0-9._-]+\.js)', html)
    js_files = list(set(js_files))
    print(f"Searching {len(js_files)} JS files for graphql client & endpoint...")

    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for jf in js_files:
            url = f"https://cdn.shopify.com{jf}"
            r = await s.get(url)
            # Search for endpoint string or graphql fetch
            matches = re.findall(r'["\']([a-zA-Z0-9/_.-]*graphql[a-zA-Z0-9/_.-]*)["\']', r.text)
            if matches:
                # filter out simple query names
                relevant = [m for m in matches if "/" in m or ".json" in m]
                if relevant:
                    print(f"{jf} -> {relevant}")
            
            # Check for header names like x-shopify-checkout-session-token or similar
            headers = re.findall(r'["\'](X-[a-zA-Z0-9_-]+)["\']', r.text, re.IGNORECASE)
            headers = [h for h in headers if "shopify" in h.lower() or "checkout" in h.lower()]
            if headers:
                print(f"{jf} -> Headers: {set(headers)}")

if __name__ == "__main__":
    asyncio.run(find_graphql_endpoint())
