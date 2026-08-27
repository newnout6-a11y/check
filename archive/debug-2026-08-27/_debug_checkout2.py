# language: python, file: scratch/_debug_checkout2.py — GET /checkout: payment methods, terms, shipping
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def probe(root: str):
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce", "")
        print(f"\n===== {root} =====")
        r_ch = await s.get(f"{api}/checkout", headers={"Nonce": nonce}, timeout=10)
        print("GET /checkout:", r_ch.status_code)
        try:
            d = r_ch.json()
            print(json.dumps(d, indent=1, ensure_ascii=False)[:1200])
        except Exception:
            print(r_ch.text[:400])


async def main():
    for root in ("https://coachconnectaustralia.com.au",
                 "https://magnesiumshop.nl",
                 "https://atriumcoffeeroasters.com"):
        try:
            await probe(root)
        except Exception as e:
            print(root, "->", type(e).__name__, e)


if __name__ == "__main__":
    asyncio.run(main())
