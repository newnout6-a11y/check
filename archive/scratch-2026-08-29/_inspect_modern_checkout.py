import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_checkout():
    url = "https://epomaker.myshopify.com"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Products
        r = await s.get(f"{url}/products.json?limit=50")
        products = r.json().get("products", [])
        variant_id = None
        for p in products:
            for v in p.get("variants", []):
                if v.get("available") and float(v.get("price", "999")) <= 5:
                    variant_id = v["id"]
                    print(f"Chosen variant: {variant_id} (${v.get('price')}) - {p.get('title')}")
                    break
            if variant_id:
                break
        
        if not variant_id:
            variant_id = products[0]["variants"][0]["id"]
            
        # 2. Add to cart
        r_add = await s.post(f"{url}/cart/add.js", json={"items": [{"id": variant_id, "quantity": 1}]})
        print(f"Cart add status: {r_add.status_code}")
        
        # 3. Checkout
        r_chk = await s.get(f"{url}/checkout", allow_redirects=True)
        print(f"Checkout status: {r_chk.status_code}, URL: {r_chk.url}")
        
        # Save HTML for inspection
        with open("scratch/checkout_page.html", "w", encoding="utf-8") as f:
            f.write(r_chk.text)
        print(f"Saved scratch/checkout_page.html ({len(r_chk.text)} bytes)")
        
        # Look for tokens, scripts, and GraphQL
        print("\n--- Key regex patterns in checkout HTML ---")
        tokens = {
            "checkout_token": re.findall(r'["\'](hWNG[a-zA-Z0-9_-]+)["\']', r_chk.text),
            "storefront_token": re.findall(r'["\']([a-f0-9]{32})["\']', r_chk.text),
            "shopify_checkout": re.findall(r'Shopify\.Checkout\s*=\s*({.*?});', r_chk.text),
            "script_srcs": re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r_chk.text),
            "form_actions": re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', r_chk.text),
            "data_schema": re.findall(r'data-schema=["\']([^"\']+)["\']', r_chk.text),
            "json_data": re.findall(r'<script id=["\']([^"\']+)["\'] type=["\']application/json["\']>([^<]+)</script>', r_chk.text),
        }
        for k, v in tokens.items():
            if k == "json_data":
                print(f"{k}: found {[item[0] for item in v]}")
            elif k == "script_srcs":
                print(f"{k}: found {len(v)} scripts -> {[s for s in v if 'checkout' in s or 'payment' in s or 'storefront' in s][:5]}")
            else:
                print(f"{k}: {v[:3]}")

if __name__ == "__main__":
    asyncio.run(inspect_checkout())
