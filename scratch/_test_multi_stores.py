import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

STORES = [
    "https://thequeenbeads.myshopify.com",
    "https://kbdfans.myshopify.com",
    "https://puravidabracelets.myshopify.com",
    "https://the-cajun-girl-pattern-shop.myshopify.com",
    "https://southwest-laundry-2.myshopify.com",
]

async def check(store):
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            r_prod = await s.get(f"{store}/products.json?limit=5", timeout=10)
            if r_prod.status_code != 200:
                print(f"[{store}] Failed /products.json -> {r_prod.status_code}")
                return
            products = r_prod.json().get("products", [])
            if not products:
                print(f"[{store}] No products found")
                return
            v_id = products[0]["variants"][0]["id"]
            
            r_add = await s.post(f"{store}/cart/add.js", json={"items": [{"id": v_id, "quantity": 1}]}, timeout=10)
            print(f"[{store}] Add to cart: {r_add.status_code}")
            
            r_chk = await s.get(f"{store}/checkout", allow_redirects=True, timeout=15)
            print(f"[{store}] Checkout URL: {r_chk.url} (status {r_chk.status_code})")
            
            html = r_chk.text
            
            # Find meta tags
            meta_tags = re.findall(r'<meta[^>]+name=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', html)
            meta_tags += re.findall(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']([^"\']+)["\']', html)
            
            names = [m[0] for m in meta_tags]
            print(f"[{store}] Meta tags found ({len(names)}): {[n for n in names if 'token' in n.lower() or 'session' in n.lower() or 'source' in n.lower() or 'shopify' in n.lower()]}")
            
            # Check for form authenticity_token
            auth_tokens = re.findall(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', html)
            if not auth_tokens:
                auth_tokens = re.findall(r'value=["\']([^"\']+)["\']\s+name=["\']authenticity_token["\']', html)
            print(f"[{store}] Authenticity tokens: {len(auth_tokens)}")
            
            # Check for payment gateway inputs
            gateways = re.findall(r'name=["\']checkout\[payment_gateway\]["\']\s+value=["\']([^"\']+)["\']', html)
            if not gateways:
                gateways = re.findall(r'data-subfields-for-gateway=["\']([^"\']+)["\']', html)
            print(f"[{store}] Gateways: {gateways}")
            
    except Exception as e:
        print(f"[{store}] Error: {e}")

async def main():
    for s in STORES:
        await check(s)

if __name__ == "__main__":
    asyncio.run(main())
