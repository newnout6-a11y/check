# language: python, file: scratch/_dump_engine_body.py — печатает точный checkout_body движка
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
        await s.post(f"{api}/cart/add-item",
                     params={"id": prod["id"], "quantity": "1"},
                     headers={"Nonce": nonce}, timeout=10)

        # === движковый шаг: выбор shipping-rate ===
        try:
            r_car2 = await s.get(f"{api}/cart", headers={"Nonce": nonce}, timeout=10)
            c2 = r_car2.json()
            print("needs_shipping:", c2.get("needs_shipping"))
            print("shipping_rates:", json.dumps(c2.get("shipping_rates"), indent=1)[:600])
            if c2.get("needs_shipping"):
                rate_id = None
                for grp in c2.get("shipping_rates") or []:
                    for rt in grp.get("shipping_rates") or []:
                        rate_id = rt.get("rate_id")
                        break
                    if rate_id:
                        break
                if rate_id:
                    r_sel = await s.post(f"{api}/cart/select-shipping-rate",
                                         json={"rate_id": rate_id},
                                         headers={"Nonce": nonce}, timeout=10)
                    print("select-rate:", r_sel.status_code)
        except Exception as e:
            print("rate select failed:", e)

        pk = ""
        for path in ("/checkout/", "/", "/shop/"):
            r0 = await s.get(root + path, timeout=10)
            pk = gc.extract_pk_live(r0.text)
            if pk:
                break

        # реплицирую телеметрию движка ПОСЛЕ country-align (US → NL)
        telem = gc.stripe_telemetry(root, pk)  # country_code default US
        country = telem.get("country") or "US"
        r_draft = await s.get(f"{api}/checkout", headers={"Nonce": nonce}, timeout=10)
        shop_country = ((r_draft.json().get("billing_address") or {}).get("country") or "").upper()
        if len(shop_country) == 2 and shop_country != country:
            country = shop_country
            telem.update(gc.geo_identity_fields(country))
        ident = {**gc.random_identity(country), **gc.geo_identity_fields(country)}

        body = {
            "billing_address": {
                "first_name": telem.get("first_name") or ident.get("first_name", "James"),
                "last_name": telem.get("last_name") or ident.get("last_name", "Carter"),
                "company": "",
                "address_1": telem.get("address_1") or ident.get("line1", ""),
                "address_2": "",
                "city": telem.get("city") or ident.get("city", ""),
                "state": ident.get("state", ""),
                "postcode": telem.get("postal_code", ""),
                "country": country,
                "email": telem.get("email") or ident.get("email", ""),
                "phone": (telem.get("phone") or ident.get("phone")
                          or f"+3 555 {111} {2222}"),
            },
            "shipping_address": {
                "first_name": telem.get("first_name") or ident.get("first_name", "James"),
                "last_name": telem.get("last_name") or ident.get("last_name", "Carter"),
                "company": "",
                "address_1": telem.get("address_1") or ident.get("line1", ""),
                "address_2": "",
                "city": telem.get("city") or ident.get("city", ""),
                "state": ident.get("state", ""),
                "postcode": telem.get("postal_code", ""),
                "country": country,
                "phone": "",
            },
            "customer_note": "", "create_account": False, "terms": True,
            "payment_method": "stripe",
        }
        # вариант A: shipping c пустым phone (как движок)
        print("telem keys:", sorted(telem.keys()))
        print("country:", country)
        print(json.dumps(body, indent=1, ensure_ascii=False))

        probe = gc.gen_probe_card()
        card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(gc.parse_card(card_raw), telem, root),
                             headers=gc.TOKENIZE_HEADERS, timeout=8)
        pm_id = r_tok.json()["id"]
        body["payment_data"] = [
            {"key": "wc-stripe-payment-method", "value": pm_id},
            {"key": "wc-stripe-payment-type", "value": "card"},
        ]
        r_co = await s.post(f"{api}/checkout", json=body,
                            headers={"Nonce": nonce}, timeout=25)
        print("\ncheckout (A: shipping phone empty):", r_co.status_code)
        print(r_co.text[:500])

        # вариант B: shipping без ключа phone вообще
        body["shipping_address"].pop("phone", None)
        r_co2 = await s.post(f"{api}/checkout", json=body,
                             headers={"Nonce": nonce}, timeout=25)
        print("\ncheckout (B: no shipping phone key):", r_co2.status_code)
        print(r_co2.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
