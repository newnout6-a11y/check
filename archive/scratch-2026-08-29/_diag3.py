# -*- coding: utf-8 -*-
import asyncio, json, os, sys, re
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def magnesium_deep():
    root = "https://magnesiumshop.nl"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nn = r_cart.headers.get("nonce")
        cartj = r_cart.json()
        pm = cartj.get("payment_methods")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nn}, timeout=10)
        nn = r_prod.headers.get("nonce") or nn
        cand = sorted((p for p in r_prod.json() if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        p0 = cand[0]
        r_add = await s.post(f"{api}/cart/add-item", params={"id": p0["id"], "quantity": "1"}, headers={"Nonce": nn}, timeout=10)
        nn = r_add.headers.get("nonce") or nn
        addj = r_add.json()
        print("needs_shipping:", addj.get("needs_shipping"))
        # update-customer с NL-адресом (боевой путь)
        addr = gc.geo_identity_fields("NL"); ident = gc.random_identity("NL")
        r_uc = await s.post(f"{api}/cart/update-customer", json={"shipping_address": {
            "first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
            "address_1": addr["line1"], "address_2": "", "city": addr["city"], "state": addr["state"],
            "postcode": addr["postal_code"], "country": "NL", "phone": ""}},
            headers={"Nonce": nn}, timeout=10)
        nn = r_uc.headers.get("nonce") or nn
        print("update-customer:", r_uc.status_code)
        r_car2 = await s.get(f"{api}/cart", headers={"Nonce": nn}, timeout=10)
        nn = r_car2.headers.get("nonce") or nn
        c2 = r_car2.json()
        rates = [(r.get("rate_id"), r.get("price")) for g in (c2.get("shipping_rates") or []) for r in (g.get("shipping_rates") or [])]
        print("rates:", rates[:4])
        if rates:
            r_sr = await s.post(f"{api}/cart/select-shipping-rate", json={"rate_id": rates[0][0]}, headers={"Nonce": nn}, timeout=10)
            nn = r_sr.headers.get("nonce") or nn
            print("select-rate:", r_sr.status_code)
        # checkout с billing+shipping NL и stripe_cc
        body = {"billing_address": {"first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
            "address_1": addr["line1"], "address_2": "", "city": addr["city"], "state": addr["state"],
            "postcode": addr["postal_code"], "country": "NL", "email": ident["email"], "phone": "+31 20 555 0123"},
            "shipping_address": {"first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
            "address_1": addr["line1"], "address_2": "", "city": addr["city"], "state": addr["state"],
            "postcode": addr["postal_code"], "country": "NL", "phone": "+31 20 555 0123"},
            "customer_note": "", "create_account": False, "terms": True,
            "payment_method": "stripe_cc",
            "payment_data": [{"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                             {"key": "wc-stripe-payment-type", "value": "card"}]}
        r_co = await s.post(f"{api}/checkout", json=body, headers={"Nonce": nn}, timeout=20)
        d = r_co.json() if r_co.status_code != 200 else {}
        print("checkout:", r_co.status_code, "code:", d.get("code"))
        print("  message:", str(d.get("message"))[:150])
        print("  params:", json.dumps(d.get("data", {}).get("params"), ensure_ascii=False)[:600])

async def wisdom_add_variants():
    root = "https://wisdomofplanets.com"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nn = r_cart.headers.get("nonce")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nn}, timeout=10)
        nn = r_prod.headers.get("nonce") or nn
        cand = sorted((p for p in r_prod.json() if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        p0 = cand[0]
        # вариант A: json body
        r_a = await s.post(f"{api}/cart/add-item", json={"id": p0["id"], "quantity": 1}, headers={"Nonce": nn}, timeout=10)
        print("add-item json-body:", r_a.status_code, "content-type:", r_a.headers.get("content-type", "?"))
        try:
            j = r_a.json(); print("  items:", len(j.get("items", [])))
        except Exception:
            print("  body head:", r_a.text[:120].replace(chr(10), " "))

async def main():
    await magnesium_deep()
    print()
    await wisdom_add_variants()

asyncio.run(main())
