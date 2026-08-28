import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

STORES = [
    "https://ticklemychi.myshopify.com",
    "https://kbdfans.myshopify.com",
    "https://epomaker.myshopify.com",
    "https://json-ld-for-seo-demo.myshopify.com",
]

async def test_store(store_url):
    print(f"\n==================== Testing: {store_url} ====================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # Step 1: Products
        try:
            r = await s.get(f"{store_url}/products.json?limit=250", timeout=10)
            print(f"[1] /products.json -> status {r.status_code}")
            if r.status_code != 200:
                print(f"Failed to get products: {r.text[:100]}")
                return
            data = r.json()
            products = data.get("products", [])
            print(f"    Found {len(products)} products")
            
            # Find cheapest available variant
            candidates = []
            for p in products:
                for v in p.get("variants", []):
                    if v.get("available"):
                        try:
                            price_cents = int(round(float(v.get("price", "999999")) * 100))
                            candidates.append({
                                "id": v["id"],
                                "title": f"{p.get('title')} - {v.get('title')}",
                                "price_cents": price_cents,
                                "price_str": v.get("price"),
                                "requires_shipping": v.get("requires_shipping", True),
                            })
                        except Exception:
                            pass
            
            if not candidates:
                print("    No available variants found!")
                return
            
            candidates.sort(key=lambda x: x["price_cents"])
            cheapest = candidates[0]
            print(f"    Cheapest: {cheapest['title']} @ {cheapest['price_str']} ({cheapest['price_cents']}c)")
            
            # Step 2: Add to Cart
            r_add = await s.post(
                f"{store_url}/cart/add.js",
                json={"items": [{"id": cheapest["id"], "quantity": 1}]},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=10
            )
            print(f"[2] /cart/add.js -> status {r_add.status_code}")
            if r_add.status_code not in (200, 201):
                # Fallback to form data
                r_add = await s.post(
                    f"{store_url}/cart/add.js",
                    data={"id": cheapest["id"], "quantity": 1},
                    timeout=10
                )
                print(f"    fallback form-data -> status {r_add.status_code}")
            
            # Step 3: Checkout Redirect
            r_chk = await s.get(
                f"{store_url}/checkout",
                allow_redirects=True,
                timeout=15
            )
            print(f"[3] /checkout -> status {r_chk.status_code} | final URL: {r_chk.url}")
            
            # Check for Cloudflare / Turnstile
            for mark in ["challenge-platform", "cf-turnstile-wrapper", "Just a moment...", "Attention Required!"]:
                if mark in r_chk.text:
                    print(f"    [!] Cloudflare challenge mark found: {mark}")
            
            # Inspect HTML for authenticity_token and payment_gateway
            auth_token_m = re.search(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', r_chk.text)
            if not auth_token_m:
                auth_token_m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']authenticity_token["\']', r_chk.text)
            
            auth_token = auth_token_m.group(1) if auth_token_m else None
            print(f"    authenticity_token: {auth_token[:20] + '...' if auth_token else 'None'}")
            
            # Find payment gateways
            gw_matches = re.findall(r'name=["\']checkout\[payment_gateway\]["\']\s+value=["\']([^"\']+)["\']', r_chk.text)
            if not gw_matches:
                gw_matches = re.findall(r'data-subfields-for-gateway=["\']([^"\']+)["\']', r_chk.text)
            if not gw_matches:
                gw_matches = re.findall(r'data-select-gateway=["\']([^"\']+)["\']', r_chk.text)
            if not gw_matches:
                gw_matches = re.findall(r'data-gateway-group=["\']([^"\']+)["\']', r_chk.text)
            
            print(f"    payment gateways: {gw_matches}")
            
            # Check if Shopify JS checkout object exists
            chk_obj_m = re.search(r'Shopify\.Checkout\s*=\s*(\{.*?\});\n', r_chk.text, re.DOTALL)
            if chk_obj_m:
                print(f"    Shopify.Checkout object present: {chk_obj_m.group(1)[:100]}...")
            
        except Exception as e:
            print(f"Error testing {store_url}: {e}")

async def main():
    for s in STORES:
        await test_store(s)

if __name__ == "__main__":
    asyncio.run(main())
