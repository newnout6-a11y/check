import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_full_checkout_flow(store_url):
    print(f"\n=================== TESTING CHECKOUT FLOW ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Products
        r_prod = await s.get(f"{store_url}/products.json?limit=50")
        products = r_prod.json().get("products", [])
        variant_id = None
        price_cents = 0
        title = ""
        for p in products:
            for v in p.get("variants", []):
                if v.get("available"):
                    variant_id = v["id"]
                    price_cents = int(round(float(v.get("price", "999")) * 100))
                    title = p.get("title")
                    break
            if variant_id:
                break
        
        print(f"Product: {title} (ID: {variant_id}, Price: {price_cents}c)")
        
        # 2. Add to Cart
        r_add = await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": variant_id, "quantity": 1}]})
        print(f"Add to cart status: {r_add.status_code}")
        
        # 3. GET /checkout
        r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True)
        chk_url = r_chk.url
        print(f"Checkout URL: {chk_url} (status: {r_chk.status_code})")
        
        # Extract checkout token from URL
        m_tok = re.search(r'/checkouts/(?:cn/|c/)?([a-zA-Z0-9_-]+)', chk_url)
        chk_token = m_tok.group(1) if m_tok else None
        print(f"Checkout Token: {chk_token}")
        
        # 4. Tokenize Card on deposit.us.shopifycs.com
        cc_parts = TEST_CARD.split("|")
        card_payload = {
            "credit_card": {
                "number": cc_parts[0],
                "first_name": "James",
                "last_name": "Smith",
                "month": cc_parts[1],
                "year": cc_parts[2],
                "verification_value": cc_parts[3]
            }
        }
        r_vault = await s.post(
            "https://deposit.us.shopifycs.com/sessions",
            json=card_payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        print(f"Vault status: {r_vault.status_code}")
        vault_data = r_vault.json()
        session_id = vault_data.get("id")
        print(f"Vault Session ID (s): {session_id}")
        
        # 5. Check if it's 3-step checkout or one-page checkout
        # Let's inspect form action, authenticity_token, payment_gateway
        html = r_chk.text
        
        # Extract authenticity_token
        auth_m = re.search(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', html)
        if not auth_m:
            auth_m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']authenticity_token["\']', html)
        auth_token = auth_m.group(1) if auth_m else ""
        print(f"authenticity_token: {auth_token[:20]}..." if auth_token else "authenticity_token: Not in HTML")
        
        # Extract payment gateway ID
        gw_ids = re.findall(r'name=["\']checkout\[payment_gateway\]["\']\s+value=["\']([^"\']+)["\']', html)
        if not gw_ids:
            gw_ids = re.findall(r'data-subfields-for-gateway=["\']([^"\']+)["\']', html)
        if not gw_ids:
            gw_ids = re.findall(r'data-select-gateway=["\']([^"\']+)["\']', html)
        print(f"Payment Gateways: {gw_ids}")
        
        # Check for serialized-sessionToken (One-page checkout SPA)
        sess_token_m = re.search(r'name=["\']serialized-sessionToken["\']\s+content=["\']([^"\']+)["\']', html)
        if sess_token_m:
            sess_token = json.loads(sess_token_m.group(1).replace("&quot;", '"'))
            print(f"One-page serialized-sessionToken found: {sess_token[:30]}...")

if __name__ == "__main__":
    asyncio.run(test_full_checkout_flow("https://epomaker.myshopify.com"))
