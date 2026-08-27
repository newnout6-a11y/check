# language: python, file: scratch/_debug_engine2.py — перехват тела checkout из движка
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

# monkeypatch: перехватываем post к /checkout и печатаем тело
_orig_post = AsyncSession.post


async def patched_post(self, url, **kw):
    if "/checkout" in str(url) and kw.get("json"):
        print(">>> POST checkout body:")
        print(json.dumps(kw["json"], indent=1, ensure_ascii=False)[:1200])
    return await _orig_post(self, url, **kw)


AsyncSession.post = patched_post


async def main():
    root = "https://magnesiumshop.nl"
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        res = await gc.store_api_confirm(s, root, "", card_raw, country="US",
                                         max_price_cents=3000)
    print("\nRESULT:", res.get("status"), "|", res.get("detail"))


if __name__ == "__main__":
    asyncio.run(main())
