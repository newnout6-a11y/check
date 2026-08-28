# -*- coding: utf-8 -*-
# Диагностика store_api цепочки: каждый шаг с телом ответа
import asyncio, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def diag(root, max_price=2000):
    print(f"===== {root} =====")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # pk
        pk = ""
        for path in ("/", "/checkout/", "/shop/"):
            r0 = await s.get(root + path, timeout=12)
            pk = gc.extract_pk_live(r0.text) or ""
            if pk:
                print(f"pk_live: {pk[:20]}... (from {path})")
                break
        if not pk:
            print("NO PK"); return
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce") or r_cart.headers.get("Nonce") or ""
        print(f"GET /cart: {r_cart.status_code}, nonce={'yes' if nonce else 'NO'}")
        cart = r_cart.json()
        print(f"  cart items: {len(cart.get('items', []))}, needs_shipping: {cart.get('needs_shipping')}")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nonce}, timeout=10)
        nn = r_prod.headers.get("nonce") or nonce
        items = r_prod.json()
        cand = sorted((p for p in items if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        print(f"products: {len(items)}, cheapest under cap: {[ (p['id'], p['prices']['price']) for p in cand[:3] ]}")
        if not cand or int(cand[0]["prices"]["price"]) > max_price:
            print("NO PRODUCT UNDER CAP"); return
        p0 = cand[0]
        r_add = await s.post(f"{api}/cart/add-item", params={"id": p0["id"], "quantity": "1"},
                             headers={"Nonce": nn}, timeout=10)
        nn = r_add.headers.get("nonce") or nn
        print(f"add-item {p0['id']}: {r_add.status_code}")
        try:
            addj = r_add.json()
            print(f"  items in cart now: {len(addj.get('items', []))}")
            for it in addj.get("items", []):
                print(f"    - {it.get('name','?')} qty={it.get('quantity')}")
        except Exception:
            print("  body:", r_add.text[:200])
        # повторный GET /cart
        r_car2 = await s.get(f"{api}/cart", headers={"Nonce": nn}, timeout=10)
        nn = r_car2.headers.get("nonce") or nn
        c2 = r_car2.json()
        print(f"re-GET /cart: items={len(c2.get('items', []))}, totals={c2.get('totals', {}).get('total_price')}")
        # драфт чекаута
        r_draft = await s.get(f"{api}/checkout", headers={"Nonce": nn}, timeout=10)
        nn = r_draft.headers.get("nonce") or nn
        draft = r_draft.json()
        print(f"GET /checkout draft keys: {sorted(draft.keys())[:12]}")
        # попытка checkout минимальным телом
        addr = gc.geo_identity_fields("NL")
        ident = gc.random_identity("NL")
        body = {
            "billing_address": {"first_name": ident["first_name"], "last_name": ident["last_name"],
                "company": "", "address_1": addr["line1"], "address_2": "", "city": addr["city"],
                "state": addr["state"], "postcode": addr["postal_code"], "country": "NL",
                "email": ident["email"], "phone": "+31 20 555 0123"},
            "customer_note": "", "create_account": True, "terms": True,
            "payment_method": "stripe",
            "payment_data": [
                {"key": "wc-stripe-payment-method", "value": "pm_card_visa_chargeDeclined"},
                {"key": "wc-stripe-payment-type", "value": "card"},
            ],
        }
        # если корзина требует shipping — добавим
        if c2.get("needs_shipping"):
            body["shipping_address"] = dict(body["billing_address"])
        r_co = await s.post(f"{api}/checkout", json=body, headers={"Nonce": nn}, timeout=20)
        print(f"POST /checkout: {r_co.status_code}")
        try:
            d = r_co.json()
            print("  code:", d.get("code"))
            print("  message:", str(d.get("message"))[:200])
            print("  data.params:", json.dumps(d.get("data", {}).get("params"), ensure_ascii=False)[:400])
            print("  additional_fields in draft?", "additional_fields" in json.dumps(draft)[:5000])
        except Exception:
            print("  body:", r_co.text[:300])
        # смотрим draft на предмет terms-полей
        for k in ("additional_fields", "checkout_fields", "needs_terms"):
            if k in draft:
                print(f"draft.{k}:", json.dumps(draft[k], ensure_ascii=False)[:500])

async def main():
    await diag("https://magnesiumshop.nl")
    print()
    await diag("https://coachconnectaustralia.com.au")
    print()
    await diag("https://wisdomofplanets.com")

asyncio.run(main())
