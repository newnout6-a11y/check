import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

async def dump_mutations():
    js_files = [
        "/cdn/shopifycloud/checkout-web/assets/c1/useAddressMutationsWithNegotiation.BfKOZi5E.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/PaymentMethods.W_eR1SBI.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/page-Payment.Cjo9iUBZ.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/actions.Cggw45rF.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/CheckoutEditorBridge.BSejiGZN.js",
    ]
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for jf in js_files:
            url = f"https://cdn.shopify.com{jf}"
            r = await s.get(url)
            text = r.text
            # Find all occurrences of mutation ...
            muts = re.findall(r'(mutation\s+[a-zA-Z0-9_]+[^{]*\{.*?\n?\s*\}\s*\})', text)
            if not muts:
                # regex across minified text
                muts = re.findall(r'mutation\s+[a-zA-Z0-9_]+(?:\([^\)]*\))?\{[^\}]+\}', text)
            print(f"\n=================== {jf} ===================")
            print(f"Found {len(muts)} mutations:")
            for m in muts:
                print("\n--- MUTATION ---")
                print(m)

if __name__ == "__main__":
    asyncio.run(dump_mutations())
