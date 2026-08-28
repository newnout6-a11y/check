# -*- coding: utf-8 -*-
import asyncio, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def main():
    root = "https://magnesiumshop.nl"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nn = r_cart.headers.get("nonce")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nn}, timeout=10)
        nn = r_prod.headers.get("nonce") or nn
        cand = sorted((p for p in r_prod.json() if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        p0 = cand[0]
        r_add = await s.post(f"{api}/cart/add-item", params={"id": p0["id"], "quantity": "1"}, headers={"Nonce": nn}, timeout=10)
        nn = r_add.headers.get("nonce") or nn
        addr = gc.geo_identity_fields("NL"); ident = gc.random_identity("NL")
        # split line1 "Damstraat 42" -> street_name + house_number
        street, num = addr["line1"].rsplit(" ", 1)
        mk = lambda extra: {
            "first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
            "address_1": addr["line1"], "address_2": "", "city": addr["city"], "state": addr["state"],
            "postcode": addr["postal_code"], "country": "NL", "email": ident["email"],
            "phone": "+31 20 555 0123", **extra}
        for name, extra in [
            ("street_name+house_number", {"street_name": street, "house_number": num}),
            ("only street_name", {"street_name": street}),
        ]:
            body = {"billing_address": mk(extra), "shipping_address": mk(extra),
                "customer_note": "", "create_account": False, "terms": True,
                "payment_method": "stripe_cc",
                "payment_data": [{"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                                 {"key": "wc-stripe-payment-type", "value": "card"}]}
            r_co = await s.post(f"{api}/checkout", json=body, headers={"Nonce": nn}, timeout=20)
            nn = r_co.headers.get("nonce") or nn
            try: d = r_co.json()
            except Exception: d = {}
            print(f"[{name}] {r_co.status_code} code={d.get('code')}")
            print("  msg:", str(d.get('message'))[:120])
            print("  params:", json.dumps(d.get('data', {}).get('params'), ensure_ascii=False)[:300])
            if d.get("code") != "rest_invalid_param":
                break

asyncio.run(main())
