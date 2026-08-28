import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_context_browser():
    url = "https://cdn.shopify.com/cdn/shopifycloud/checkout-web/assets/c1/context-browser.BPh2Xdws.js"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(url)
        text = r.text
        print("Total length:", len(text))
        
        # Look for fetch or XMLHttpRequest calls
        matches = re.findall(r'fetch\([^\)]+\)', text)
        print("fetch calls:", len(matches))
        for m in matches[:5]:
            print("  ", m[:150])
            
        # Look for path building
        paths = re.findall(r'["\'](/[^"\']+)["\']', text)
        print("Paths:", [p for p in set(paths) if not p.endswith(".js") and not p.endswith(".css")][:10])

if __name__ == "__main__":
    asyncio.run(inspect_context_browser())
