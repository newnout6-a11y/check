# language: python, file: scratch/_debug_checkout.py — разбор invalid payment_method на одном гейте
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://wisdomofplanets.com"
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce", "")
        print("cart:", r_cart.status_code, "nonce:", bool(nonce))
        cart = r_cart.json()
        print("items:", [(i["name"], i["totals"]) for i in cart.get("items", [])])
        print("shipping rates:", cart.get("shipping_rates"))

        r_prod = await s.get(f"{api}/products", params={"per_page": 100},
                             headers={"Nonce": nonce}, timeout=10)
        items = r_prod.json()
        cand = sorted((p for p in items
                       if p.get("prices", {}).get("price")
                       and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        print("cheapest 5:", [(p["name"][:30], p["prices"]["price"],
                               p.get("is_purchasable"), p.get("has_options")) for p in cand[:5]])
        prod = cand[0]
        r_add = await s.post(f"{api}/cart/add-item",
                             params={"id": prod["id"], "quantity": "1"},
                             headers={"Nonce": nonce}, timeout=10)
        print("add-item:", r_add.status_code)

        # после add-item корзина знает shipping-методы?
        r_cart2 = await s.get(f"{api}/cart", headers={"Nonce": nonce}, timeout=10)
        c2 = r_cart2.json()
        print("need shipping:", c2.get("needs_shipping"))
        for i in c2.get("shipping_rates", []):
            print("  rate:", i.get("rate_id"), i.get("rate_name"), i.get("rate_price"))

        # pk + токенизация
        pk = ""
        for path in ("/checkout/", "/", "/shop/"):
            r0 = await s.get(root + path, timeout=10)
            pk = gc.extract_pk_live(r0.text)
            if pk:
                break
        print("pk:", pk[:24])
        telem = gc.stripe_telemetry(root, pk)
        probe = gc.gen_probe_card()
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(probe, telem, root),
                             headers=gc.TOKENIZE_HEADERS, timeout=8)
        tok = r_tok.json()
        print("tokenize:", "id" in tok, tok.get("id", tok.get("error", {}).get("code")))

        ident = {**gc.random_identity("US"), **gc.geo_identity_fields("US")}
        body = {
            "billing_address": {
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident.get("line1", "123 Main St"),
                "address_2": "", "city": ident.get("city", "New York"),
                "state": ident.get("state", "NY"),
                "postcode": ident.get("postal_code", "10001"),
                "country": "US", "email": ident["email"], "phone": "+1 555 010 0101",
            },
            "shipping_address": {  # дубль биллинга — физические товары
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident.get("line1", "123 Main St"),
                "address_2": "", "city": ident.get("city", "New York"),
                "state": ident.get("state", "NY"),
                "postcode": ident.get("postal_code", "10001"),
                "country": "US",
            },
            "customer_note": "", "create_account": False,
            "payment_method": "stripe",
            "payment_data": [
                {"key": "wc-stripe-payment-method", "value": tok["id"]},
                {"key": "wc-stripe-payment-type", "value": "card"},
            ],
        }
        # выбранный shipping rate, если корзина его требует
        rate_ids = []
        for grp in c2.get("shipping_rates", []):
            for rt in grp.get("shipping_rates", []):
                rate_ids.append(rt.get("rate_id"))
        if rate_ids:
            body["shipping_address"]["selected_rate"] = ...
        r_co = await s.post(f"{api}/checkout", json=body,
                            headers={"Nonce": nonce}, timeout=25)
        print("\ncheckout:", r_co.status_code)
        print(r_co.text[:1500])


if __name__ == "__main__":
    asyncio.run(main())
