import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

async def test_graphql_negotiation(store_url):
    print(f"\n=================== Testing GraphQL Negotiation on {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Product & Cart
        r_prod = await s.get(f"{store_url}/products.json?limit=10")
        products = r_prod.json().get("products", [])
        variant_id = products[0]["variants"][0]["id"]
        
        await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": variant_id, "quantity": 1}]})
        
        # 2. Checkout GET
        r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True)
        chk_url = r_chk.url
        html = r_chk.text
        
        # Extract meta tokens
        def get_meta(name):
            m = re.search(rf'name=["\']{name}["\']\s+content=["\']([^"\']+)["\']', html)
            if not m:
                m = re.search(rf'content=["\']([^"\']+)["\']\s+name=["\']{name}["\']', html)
            if m:
                c = m.group(1).replace("&quot;", '"')
                try:
                    return json.loads(c)
                except Exception:
                    return c
            return None
        
        session_token = get_meta("serialized-sessionToken")
        source_token = get_meta("serialized-sourceToken")
        source_type = get_meta("serialized-sourceType")
        shopify_y = get_meta("serialized-shopifyY")
        shopify_s = get_meta("serialized-shopifyS")
        
        print(f"session_token: {str(session_token)[:30]}...")
        print(f"source_token: {source_token}")
        print(f"source_type: {source_type}")
        
        # Endpoints to test
        endpoints = [
            f"{store_url}/api/2024-07/graphql.json",
            f"{store_url}/api/2024-10/graphql.json",
            f"{store_url}/api/graphql.json",
            f"{store_url}/checkouts/{source_type}/{source_token}",
            f"{store_url}/checkouts/unstable/graphql",
            f"https://checkout.shopify.com/api/graphql.json",
        ]
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Checkout-One-Session-Token": session_token or "",
            "X-Shopify-Checkout-Session-Token": session_token or "",
            "X-Shopify-UniqueToken": shopify_y or "",
            "X-Shopify-VisitToken": shopify_s or "",
            "Origin": store_url,
            "Referer": chk_url,
        }
        
        query = """
        query {
            shop {
                name
            }
        }
        """
        
        for ep in endpoints:
            try:
                r_ep = await s.post(ep, json={"query": query}, headers=headers, timeout=5)
                print(f"POST {ep} -> Status: {r_ep.status_code}, Body: {r_ep.text[:150]}")
            except Exception as e:
                print(f"POST {ep} -> Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_graphql_negotiation("https://epomaker.myshopify.com"))
