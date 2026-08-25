# language: Python 3.12+, file: scratch/_probe_store_api.py, target: Windows 11
# Learn the Woo Store API mint flow empirically: products -> add-item -> cart ->
# checkout POST variants. Read-only recon until the final checkout POST.
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc

ROOT = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://artisalwaysmagic.com"
API = f"{ROOT}/wp-json/wc/store/v1"

BILLING = {
    "first_name": "James", "last_name": "Carter", "company": "",
    "address_1": "742 Evergreen Terrace", "address_2": "",
    "city": "Portland", "state": "OR", "postcode": "97205", "country": "US",
    "email": "james.carter.mt84@example.com", "phone": "5035550142",
}


async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # Свежий Nonce Store API отдаёт в заголовке каждого GET /cart
        r = await s.get(f"{API}/cart", timeout=10)
        try:
            api_nonces = r.headers.get_list("nonce")
        except Exception:
            api_nonces = []
        nonce = api_nonces[0] if api_nonces else (r.headers.get("nonce") or "")
        print(f"[*] GET /cart: HTTP {r.status_code}, Nonce header: {'yes (' + nonce[:10] + '...)' if nonce else 'NO'}")
        headers = {"Nonce": nonce} if nonce else {}

        r = await s.get(f"{API}/products", params={"per_page": 5},
                        headers=headers, timeout=10)
        print(f"[*] products: HTTP {r.status_code}")
        items = r.json()
        if not isinstance(items, list) or not items:
            print(f"    body[:200]={r.text[:200]!r}")
            return
        pid = None
        for p in items:
            if p.get("prices", {}).get("price") not in (None, "0"):
                pid = p["id"]
                print(f"[*] candidate product id={pid} name={p.get('name', '')[:40]} "
                      f"price={p['prices'].get('price')}")
                break
        if pid is None:
            pid = items[0]["id"]
            print(f"[*] fallback product id={pid}")

        r = await s.post(f"{API}/cart/add-item",
                         params={"id": pid, "quantity": "1"},
                         headers=headers, timeout=10)
        print(f"[*] add-item: HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"    {r.text[:300]}")
            return

        r = await s.get(f"{API}/cart", headers=headers, timeout=10)
        cart = r.json()
        total = cart.get("totals", {})
        print(f"[*] cart: {cart.get('item_count')} items, total={total.get('total_price')} "
              f"{total.get('currency_code')}")

        # Варианты checkout POST — смотрим, чего не хватает и что отдаёт Stripe-ветка
        payloads = [
            ("minimal", {"billing_address": BILLING, "customer_note": "",
                         "create_account": False,
                         "payment_method": "stripe", "payment_data": []}),
            ("with-order-note", {"billing_address": BILLING, "shipping_address": BILLING,
                                 "customer_note": "", "create_account": False,
                                 "payment_method": "stripe",
                                 "payment_data": [
                                     {"key": "wc-stripe-payment-method", "value": ""},
                                     {"key": "wc-stripe-payment-type", "value": "card"}]}),
        ]
        for label, body in payloads:
            r = await s.post(f"{API}/checkout", json=body, headers=headers, timeout=15)
            txt = r.text
            secrets = gc.RE_CLIENT_SECRET.findall(txt)
            print(f"[checkout | {label}] HTTP {r.status_code} secrets={len(secrets)}")
            try:
                d = r.json()
                print(f"    code={d.get('code')} msg={str(d.get('message'))[:120]}")
                pr = d.get("payment_result")
                if pr:
                    print(f"    payment_result.status={pr.get('status')} "
                          f"details={json.dumps(pr.get('payment_details'))[:200]}")
            except Exception:
                print(f"    body[:150]={txt[:150]!r}")


if __name__ == "__main__":
    asyncio.run(main())
