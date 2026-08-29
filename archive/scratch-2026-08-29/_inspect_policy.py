import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_policy():
    url = "https://cdn.shopify.com/cdn/shopifycloud/checkout-web/assets/c1/checkout-policy.DnD1veXO.js"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(url)
        text = r.text
        print("Total length:", len(text))
        
        # Look for graphql URL
        matches = re.findall(r'.{0,100}api/graphql\.json.{0,100}', text)
        for m in matches:
            print("graphql match:", m)

        # Look for headers
        hdrs = re.findall(r'.{0,50}X-Checkout-.{0,50}', text)
        for h in hdrs[:5]:
            print("header context:", h)

if __name__ == "__main__":
    asyncio.run(inspect_policy())
