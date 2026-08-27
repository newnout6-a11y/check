# language: python, file: scratch/_debug_raw.py — сырой ответ /checkout на herbaura
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://herbaura.fr"
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
        await s.post(f"{api}/cart/add-item",
                     params={"id": items[0]["id"], "quantity": "1"},
                     headers={"Nonce": nonce}, timeout=10)

        pk = ""
        for path in ("/checkout/", "/", "/shop/"):
            r0 = await s.get(root + path, timeout=10)
            pk = gc.extract_pk_live(r0.text)
            if pk:
                break
        telem = gc.stripe_telemetry(root, pk)
        # страна магазина FR
        telem.update(gc.geo_identity_fields("FR"))
        probe = gc.gen_probe_card()
        card = gc.parse_card(f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}")
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(card, telem, root),
                             headers=gc.TOKENIZE_HEADERS, timeout=8)
        pm_id = r_tok.json()["id"]

        ident = {**gc.random_identity("FR"), **gc.geo_identity_fields("FR")}
        body = {
            "billing_address": {
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident["line1"], "address_2": "",
                "city": ident["city"], "state": ident["state"],
                "postcode": ident["postal_code"], "country": "FR",
                "email": ident["email"],
                "phone": f"+33 {random_phone()}",
            },
            "shipping_address": {
                "first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": ident["line1"], "address_2": "",
                "city": ident["city"], "state": ident["state"],
                "postcode": ident["postal_code"], "country": "FR",
                "phone": f"+33 {random_phone()}",
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
        print("status:", r_co.status_code)
        print("headers:", dict(r_co.headers))
        print("body[:600]:", r_co.text[:600])


def random_phone():
    import random
    return f"555 {random.randint(100, 999)} {random.randint(100, 999)}"


if __name__ == "__main__":
    asyncio.run(main())
