# -*- coding: utf-8 -*-
# Диагностика-2: payment_methods в cart, схлопывание корзины, terms-вариации
import asyncio, json, os, sys, re
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def probe(root):
    print(f"===== {root} =====")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r0 = await s.get(root + "/", timeout=12)
        m = re.search(r'<html[^>]*lang="([a-z]{2})-', r0.text, re.I)
        print("storefront lang:", m.group(1) if m else "?")
        api = f"{root}/wp-json/wc/store/v1"
        r_cart = await s.get(f"{api}/cart", timeout=10)
        cart = r_cart.json()
        nn = r_cart.headers.get("nonce") or ""
        print("cart keys:", sorted(cart.keys()))
        pm = cart.get("payment_methods") or cart.get("payment_gateways")
        print("payment_methods in cart:", json.dumps(pm, ensure_ascii=False)[:300] if pm else "NO")
        # добавим товар
        r_prod = await s.get(f"{api}/products", params={"per_page": 30}, headers={"Nonce": nn}, timeout=10)
        nn = r_prod.headers.get("nonce") or nn
        cand = sorted((p for p in r_prod.json() if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
                      key=lambda p: int(p["prices"]["price"]))
        p0 = cand[0]
        r_add = await s.post(f"{api}/cart/add-item", params={"id": p0["id"], "quantity": "1"},
                             headers={"Nonce": nn}, timeout=10)
        nn = r_add.headers.get("nonce") or nn
        addj = {}
        try: addj = r_add.json()
        except Exception: pass
        items = len(addj.get("items", [])) if addj else -1
        print(f"add-item {p0['id']}: {r_add.status_code}, items={items}, needs_shipping={addj.get('needs_shipping')}")
        # payment_methods из add-item ответа
        pm2 = addj.get("payment_methods") or addj.get("payment_gateways")
        print("payment_methods after add:", json.dumps(pm2, ensure_ascii=False)[:400] if pm2 else "NO")
        return

async def main():
    await probe("https://magnesiumshop.nl")
    print()
    await probe("https://wisdomofplanets.com")
    print()
    await probe("https://coachconnectaustralia.com.au")

asyncio.run(main())
