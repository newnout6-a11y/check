import asyncio
import json
from curl_cffi.requests import AsyncSession

CANDIDATES = [
    "https://epomaker.myshopify.com",
    "https://puravidabracelets.myshopify.com",
    "https://kbdfans.myshopify.com",
    "https://the-cajun-girl-pattern-shop.myshopify.com",
    "https://chubbies.myshopify.com",
    "https://deathwishcoffee.myshopify.com",
    "https://ticklemychi.myshopify.com",
    "https://gymshark.myshopify.com",
    "https://savvy-frugal-mom.myshopify.com",
    "https://8agujy-qp.myshopify.com",
    "https://thequeenbeads.myshopify.com",
    "https://lm-products.myshopify.com",
    "https://southwest-laundry-2.myshopify.com",
]

async def check_store(store_url):
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            r = await s.get(f"{store_url}/products.json?limit=50", timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            products = data.get("products", [])
            if not products:
                return None
            
            # Find cheapest available variant
            cheapest = None
            min_price = 9999999
            for p in products:
                for v in p.get("variants", []):
                    if v.get("available"):
                        try:
                            price_cents = int(round(float(v.get("price", "9999")) * 100))
                            if price_cents < min_price and price_cents > 0:
                                min_price = price_cents
                                cheapest = {
                                    "product_id": p.get("id"),
                                    "variant_id": v.get("id"),
                                    "product_title": p.get("title"),
                                    "variant_title": v.get("title"),
                                    "price_cents": price_cents,
                                    "price_str": v.get("price"),
                                }
                        except Exception:
                            pass
            
            if not cheapest:
                return None
            
            # Test cart add & checkout
            r_add = await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": cheapest["variant_id"], "quantity": 1}]}, timeout=8)
            if r_add.status_code not in (200, 201):
                return None
            
            r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True, timeout=10)
            if r_chk.status_code not in (200, 302):
                return None
            
            # Check for Cloudflare / Turnstile challenge
            has_cf = any(mark in r_chk.text for mark in ["challenge-platform", "cf-turnstile-wrapper", "Just a moment...", "Attention Required!"])
            
            return {
                "url": store_url,
                "domain": store_url.replace("https://", "").replace("http://", "").rstrip("/"),
                "cheapest": cheapest,
                "checkout_url": r_chk.url,
                "status_code": r_chk.status_code,
                "has_cf": has_cf,
            }
    except Exception as e:
        return None

async def main():
    print("Testing candidate stores...")
    tasks = [check_store(url) for url in CANDIDATES]
    results = await asyncio.gather(*tasks)
    valid = [r for r in results if r is not None]
    print(f"\nFound {len(valid)} working Shopify stores:")
    for v in sorted(valid, key=lambda x: x["cheapest"]["price_cents"]):
        print(f"[*] {v['url']} -> ${v['cheapest']['price_str']} ({v['cheapest']['price_cents']}c) | CF: {v['has_cf']} | Item: {v['cheapest']['product_title']}")
        
    with open("data/shopify_gates.json", "w", encoding="utf-8") as f:
        json.dump([
            {
                "url": v["url"],
                "domain": v["domain"],
                "cheapest_cents": v["cheapest"]["price_cents"],
                "cheapest_title": v["cheapest"]["product_title"],
                "variant_id": v["cheapest"]["variant_id"],
                "currency": "USD"
            } for v in valid
        ], f, indent=2, ensure_ascii=False)
    print("Saved data/shopify_gates.json")

    with open("data/shopify_targets.txt", "w", encoding="utf-8") as f:
        for v in sorted(valid, key=lambda x: x["cheapest"]["price_cents"]):
            f.write(v["url"] + "\n")
    print("Saved data/shopify_targets.txt")

if __name__ == "__main__":
    asyncio.run(main())
