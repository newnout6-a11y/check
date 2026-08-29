import asyncio
import re
from curl_cffi.requests import AsyncSession

async def find_negotiate_mutation():
    with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
        html = f.read()

    js_files = re.findall(r'(/cdn/shopifycloud/checkout-web/assets/c1/[a-zA-Z0-9._-]+\.js)', html)
    js_files = list(set(js_files))

    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for jf in js_files:
            url = f"https://cdn.shopify.com{jf}"
            r = await s.get(url)
            # Search for mutation negotiate or mutation Checkout or mutation Submit
            muts = re.findall(r'mutation\s+([a-zA-Z0-9_]+)\s*\(([^\)]*)\)\s*\{', r.text)
            if muts:
                names = [m[0] for m in muts]
                if any(n not in ["CreditCardCreate", "CreditCardCompleteVerificationAndVault", "CreditCardDelete", "CreditCardUpdate", "AddPhone"] for n in names):
                    print(f"\n{jf} -> {muts}")
                    # Print snippet around mutation
                    for n in names:
                        idx = r.text.find(f"mutation {n}")
                        if idx != -1:
                            print(f"--- Mutation {n} snippet ---")
                            print(r.text[idx:idx+400])

if __name__ == "__main__":
    asyncio.run(find_negotiate_mutation())
