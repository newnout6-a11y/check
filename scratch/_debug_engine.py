# language: python, file: scratch/_debug_engine.py — store_api_confirm напрямую, полный вывод
import asyncio
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://magnesiumshop.nl"
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        res = await gc.store_api_confirm(s, root, "", card_raw, country="US",
                                         max_price_cents=3000)
    for k, v in res.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
