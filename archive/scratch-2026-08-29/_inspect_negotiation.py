import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_negotiation():
    url = "https://cdn.shopify.com/cdn/shopifycloud/checkout-web/assets/c1/useAddressMutationsWithNegotiation.BfKOZi5E.js"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(url)
        text = r.text
        print("Total length:", len(text))
        
        # Search for full mutation strings
        mut_blocks = re.findall(r'mutation\s+[a-zA-Z0-9_]+\s*\([^\)]*\)\s*\{[^\}]+\}', text)
        print(f"Found {len(mut_blocks)} mutation definitions:")
        for mb in mut_blocks[:5]:
            print("\n", mb[:300])
            
        # Search for POST / fetch / endpoint urls
        urls = re.findall(r'["\'](/checkouts/[a-zA-Z0-9/_.-]+|/api/[a-zA-Z0-9/_.-]+)["\']', text)
        print("Endpoints in file:", list(set(urls)))

if __name__ == "__main__":
    asyncio.run(inspect_negotiation())
