# -*- coding: utf-8 -*-
# расширение пула Shopify-доноров: мердж с существующим shopify_gates.json
import asyncio
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# новые кандидаты: бренды из 2026-обзоров (wisepops/meetanshi/sitebuilderreport)
# + tavily-находки живых поддоменов + классические DTC
NEW_CANDIDATES = [
    "https://allbirds.myshopify.com",
    "https://bombas.myshopify.com",
    "https://brooklinen.myshopify.com",
    "https://casper.myshopify.com",
    "https://fashionnova.myshopify.com",
    "https://kyliecosmetics.myshopify.com",
    "https://mvmt.myshopify.com",
    "https://taylorstitch.myshopify.com",
    "https://stevemadden.myshopify.com",
    "https://aloyoga.myshopify.com",
    "https://knix.myshopify.com",
    "https://raycon.myshopify.com",
    "https://hismile.myshopify.com",
    "https://rebeccaminkoff.myshopify.com",
    "https://leesa.myshopify.com",
    "https://skims.myshopify.com",
    "https://colourpop.myshopify.com",
    "https://morphe.myshopify.com",
    "https://drsquatch.myshopify.com",
    "https://trueclassic.myshopify.com",
    "https://meundies.myshopify.com",
    "https://mackweldon.myshopify.com",
    "https://loomandartisan.myshopify.com",
    "https://lootcrate.myshopify.com",
    "https://masterclass.myshopify.com",
    "https://bruvi.myshopify.com",
    "https://cocolab.myshopify.com",
    "https://crateandbarrel.myshopify.com",
    "https://jennycraig.myshopify.com",
    "https://staples-canada.myshopify.com",
    "https://love-your-melon.myshopify.com",
    "https://soylent.myshopify.com",
    "https://quantumfl daily.myshopify.com",
    "https://ugmonk.myshopify.com",
    "https://coppercrane.myshopify.com",
    "https://tayroc.myshopify.com",
    "https://idistrict.myshopify.com",
    "https://gymsharkstore.myshopify.com",
    # tavily-находки (живые на 2026-08)
    "https://digital-products-app-demo.myshopify.com",
    "https://adam-hawley-store.myshopify.com",
    "https://dumqtw-ip.myshopify.com",
    "https://c4b979-2.myshopify.com",
]

async def check_store(store_url):
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            r = await s.get(f"{store_url}/products.json?limit=100", timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            products = data.get("products", [])
            if not products:
                return None
            cheapest = None
            min_price = 9999999
            for p in products:
                for v in p.get("variants", []):
                    if v.get("available"):
                        try:
                            pc = int(round(float(v.get("price", "9999")) * 100))
                            if 0 < pc < min_price:
                                min_price = pc
                                cheapest = {
                                    "variant_id": v.get("id"),
                                    "product_title": p.get("title"),
                                    "price_cents": pc,
                                }
                        except Exception:
                            pass
            if not cheapest:
                return None
            r_add = await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": cheapest["variant_id"], "quantity": 1}]}, timeout=8)
            if r_add.status_code not in (200, 201):
                return None
            r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True, timeout=10)
            if r_chk.status_code not in (200, 302):
                return None
            has_cf = any(mark in r_chk.text for mark in ["challenge-platform", "cf-turnstile-wrapper", "Just a moment...", "Attention Required!"])
            if has_cf:
                return None  # антибот на чекауте — не донор
            return {"url": store_url,
                    "domain": store_url.replace("https://", "").rstrip("/"),
                    "cheapest_cents": cheapest["price_cents"],
                    "cheapest_title": cheapest["product_title"],
                    "variant_id": cheapest["variant_id"],
                    "currency": "USD"}
    except Exception:
        return None

async def main():
    gates_path = os.path.join(ROOT, "data", "shopify_gates.json")
    existing = {}
    if os.path.exists(gates_path):
        with open(gates_path, encoding="utf-8") as f:
            for g in json.load(f):
                existing[g["domain"]] = g
    print(f"[pool] существующих: {len(existing)}; кандидатов: {len(NEW_CANDIDATES)}")
    results = await asyncio.gather(*[check_store(u) for u in NEW_CANDIDATES])
    fresh = [r for r in results if r is not None]
    print(f"[pool] живых из новых: {len(fresh)}")
    for v in sorted(fresh, key=lambda x: x["cheapest_cents"]):
        print(f"  + {v['domain']} -> {v['cheapest_cents']}c | {v['cheapest_title'][:50]}")
    for v in fresh:
        existing[v["domain"]] = v
    pool = sorted(existing.values(), key=lambda g: g.get("cheapest_cents", 0))
    with open(gates_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)
    targets_path = os.path.join(ROOT, "data", "shopify_targets.txt")
    with open(targets_path, "w", encoding="utf-8") as f:
        for g in pool:
            f.write(g["url"] + "\n")
    print(f"[pool] итог: {len(pool)} магазинов -> shopify_gates.json + shopify_targets.txt")

if __name__ == "__main__":
    asyncio.run(main())