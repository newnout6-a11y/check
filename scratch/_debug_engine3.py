# language: python, file: scratch/_debug_engine3.py — replay перехваченного тела один раз
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

# тело из движкового перехвата (Rotterdam, stripe_cc) — воспроизводим дословно
BODY = {
    "billing_address": {
        "first_name": "William", "last_name": "Wright", "company": "",
        "address_1": "2607 Main Street", "address_2": "",
        "city": "Utrecht", "state": "UT", "postcode": "3511 LM",
        "country": "NL", "email": "william.rnfodvn@yahoo.com",
        "phone": "+2 555 784 6285",
    },
    "shipping_address": {
        "first_name": "William", "last_name": "Wright", "company": "",
        "address_1": "2607 Main Street", "address_2": "",
        "city": "Utrecht", "state": "UT", "postcode": "3511 LM",
        "country": "NL", "phone": "",
    },
    "customer_note": "", "create_account": False, "terms": True,
    "payment_method": "stripe",
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

        # токенируем с NL-телметрией — как движок
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

        # 1) без payment_data
        b1 = json.loads(json.dumps(BODY))
        r1 = await s.post(f"{api}/checkout", json=b1,
                          headers={"Nonce": nonce}, timeout=25)
        print("no payment_data:", r1.status_code, r1.text[:200])

        # 2) с payment_data
        b2 = json.loads(json.dumps(BODY))
        b2["payment_data"] = [
            {"key": "wc-stripe-payment-method", "value": pm_id},
            {"key": "wc-stripe-payment-type", "value": "card"},
        ]
        r2 = await s.post(f"{api}/checkout", json=b2,
                          headers={"Nonce": nonce}, timeout=25)
        print("with payment_data:", r2.status_code, r2.text[:200])

        # 3) ретрай с stripe_cc — как движок после enum-ошибки
        b3 = json.loads(json.dumps(b2))
        b3["payment_method"] = "stripe_cc"
        r3 = await s.post(f"{api}/checkout", json=b3,
                          headers={"Nonce": nonce}, timeout=25)
        print("stripe_cc retry:", r3.status_code, r3.text[:300])

        # 4) ретрай без shipping phone
        b4 = json.loads(json.dumps(b3))
        b4["shipping_address"].pop("phone", None)
        r4 = await s.post(f"{api}/checkout", json=b4,
                          headers={"Nonce": nonce}, timeout=25)
        print("stripe_cc no ship-phone:", r4.status_code, r4.text[:300])


if __name__ == "__main__":
    asyncio.run(main())
