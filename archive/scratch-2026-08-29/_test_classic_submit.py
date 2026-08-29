import asyncio
import json
import re
import urllib.parse
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_store_classic_checkout(store_url):
    print(f"\n=================== TESTING CLASSIC CHECKOUT ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Get products
        r_prod = await s.get(f"{store_url}/products.json?limit=50", timeout=10)
        if r_prod.status_code != 200:
            print("Failed to get products")
            return
        products = r_prod.json().get("products", [])
        
        cheapest_variant = None
        for p in products:
            for v in p.get("variants", []):
                if v.get("available"):
                    try:
                        price = float(v.get("price", "9999"))
                        if price <= 5.0:
                            cheapest_variant = v["id"]
                            print(f"Product: {p['title']} - {v['title']} (${v['price']})")
                            break
                    except Exception:
                        pass
            if cheapest_variant:
                break
        
        if not cheapest_variant:
            cheapest_variant = products[0]["variants"][0]["id"]
            
        # 2. Add to cart
        r_add = await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": cheapest_variant, "quantity": 1}]}, timeout=10)
        print(f"Add to cart status: {r_add.status_code}")
        
        # 3. Get /checkout
        r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True, timeout=15)
        print(f"Checkout URL: {r_chk.url} (status {r_chk.status_code})")
        
        html = r_chk.text
        
        # Check if Turnstile / Cloudflare challenge
        for mark in ["challenge-platform", "cf-turnstile-wrapper", "Just a moment...", "Attention Required!"]:
            if mark in html:
                print(f"[!] Protection detected: {mark}")
                
        # 4. Extract tokens
        auth_tokens = re.findall(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', html)
        if not auth_tokens:
            auth_tokens = re.findall(r'value=["\']([^"\']+)["\']\s+name=["\']authenticity_token["\']', html)
        print(f"Auth tokens found: {len(auth_tokens)}")
        
        # Gateways
        gateways = re.findall(r'data-subfields-for-gateway=["\']([^"\']+)["\']', html)
        if not gateways:
            gateways = re.findall(r'name=["\']checkout\[payment_gateway\]["\']\s+value=["\']([^"\']+)["\']', html)
        if not gateways:
            gateways = re.findall(r'value=["\']([0-9]{5,15})["\'][^>]*name=["\']checkout\[payment_gateway\]["\']', html)
        print(f"Gateways found: {gateways}")
        
        # Check modern Checkout One metadata
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
        print(f"serialized-sessionToken: {str(session_token)[:25]}...")
        print(f"serialized-sourceToken: {source_token}")
        
        # 5. Vault card on deposit.us.shopifycs.com
        cc_num, cc_mm, cc_yy, cc_cvv = TEST_CARD.split("|")
        vault_payload = {
            "credit_card": {
                "number": cc_num,
                "first_name": "James",
                "last_name": "Smith",
                "month": cc_mm,
                "year": cc_yy,
                "verification_value": cc_cvv
            }
        }
        r_vault = await s.post(
            "https://deposit.us.shopifycs.com/sessions",
            json=vault_payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10
        )
        vault_id = r_vault.json().get("id")
        print(f"Vaulted Session ID: {vault_id}")
        
        # Let's test standard checkout form POST
        if auth_tokens and gateways:
            gw_id = gateways[0]
            token = auth_tokens[0]
            form_data = {
                "_method": "patch",
                "authenticity_token": token,
                "previous_step": "payment_method",
                "step": "",
                "s": vault_id,
                "checkout[payment_gateway]": gw_id,
                "checkout[credit_card][vault]": "default",
                "checkout[different_billing_address]": "false",
                "checkout[remember_me]": "false",
                "checkout[vault_phone]": "",
                "checkout[total_price]": "100",
                "complete": "1",
                "checkout[client_details][browser_width]": "1920",
                "checkout[client_details][browser_height]": "1080",
                "checkout[client_details][javascript_enabled]": "1",
                "checkout[client_details][color_depth]": "24",
                "checkout[client_details][java_enabled]": "false",
                "checkout[client_details][browser_tz]": "300"
            }
            headers = {
                "Origin": store_url,
                "Referer": r_chk.url,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            r_submit = await s.post(r_chk.url, data=form_data, headers=headers, allow_redirects=True, timeout=15)
            print(f"Form POST response status: {r_submit.status_code}, final URL: {r_submit.url}")
            print("Response snippet:", r_submit.text[:400])

if __name__ == "__main__":
    asyncio.run(test_store_classic_checkout("https://epomaker.myshopify.com"))
