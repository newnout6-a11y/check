# language: python, file: scratch/_debug_ext.py — extensions-контур и shipping phone для NL
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

BASE = {
    "billing_address": {
        "first_name": "Willem", "last_name": "de Vries", "company": "",
        "address_1": "Damstraat 12", "address_2": "",
        "city": "Amsterdam", "state": "NH", "postcode": "1012 AB",
        "country": "NL", "email": "willem.devries1204@hotmail.com",
        "phone": "+31 20 555 0101",
    },
    "shipping_address": {
        "first_name": "Willem", "last_name": "de Vries", "company": "",
        "address_1": "Damstraat 12", "address_2": "",
        "city": "Amsterdam", "state": "NH", "postcode": "1012 AB",
        "country": "NL", "phone": "+31 20 555 0101",
    },
    "customer_note": "", "create_account": False, "terms": True,
    "payment_method": "stripe_cc",
}


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
        telem.update(gc.geo_identity_fields("NL"))
        probe = gc.gen_probe_card()
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(probe, telem, root),
                             headers=gc.TOKENIZE_HEADERS, timeout=8)
        pm_id = r_tok.json()["id"]

        # вариант 1: billing = shipping (полный дубль с phone)
        b1 = json.loads(json.dumps(BASE))
        b1["payment_data"] = [
            {"key": "wc-stripe-payment-method", "value": pm_id},
            {"key": "wc-stripe-payment-type", "value": "card"},
        ]
        r1 = await s.post(f"{api}/checkout", json=b1,
                          headers={"Nonce": nonce}, timeout=25)
        print("full-dupl:", r1.status_code)
        print(json.dumps(r1.json(), indent=1, ensure_ascii=False)[:1500])

        # вариант 2: + extensions с NL postcode-плагином
        b2 = json.loads(json.dumps(b1))
        b2["extensions"] = {
            "dutch-postcode-address": {
                "postcode": "1012 AB", "house_number": "12",
                "street_name": "Damstraat", "city": "Amsterdam",
            }
        }
        r2 = await s.post(f"{api}/checkout", json=b2,
                          headers={"Nonce": nonce}, timeout=25)
        print("with-ext:", r2.status_code, r2.text[:300])


if __name__ == "__main__":
    asyncio.run(main())
