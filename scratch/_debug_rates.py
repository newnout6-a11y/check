# language: python, file: scratch/_debug_rates.py — структура shipping_rates cuttingfluid
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://cuttingfluid.online"
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce", "")
        r_prod = await s.get(f"{api}/products", params={"per_page": 30},
                             headers={"Nonce": nonce}, timeout=10)
        items = sorted((p for p in r_prod.json()
                        if p.get("prices", {}).get("price")
                        and int(p["prices"]["price"]) > 0),
                       key=lambda p: int(p["prices"]["price"]))
        await s.post(f"{api}/cart/add-item",
                     params={"id": items[0]["id"], "quantity": "1"},
                     headers={"Nonce": nonce}, timeout=10)
        r2 = await s.get(f"{api}/cart", headers={"Nonce": nonce}, timeout=10)
        c2 = r2.json()
        print("needs_shipping:", c2.get("needs_shipping"))
        print("shipping_rates:", json.dumps(c2.get("shipping_rates"),
                                            ensure_ascii=False)[:800])
        # есть ли rates вообще
        groups = c2.get("shipping_rates") or []
        if groups:
            g0 = groups[0]
            print("group keys:", list(g0.keys()) if isinstance(g0, dict) else type(g0))
            rates = g0.get("shipping_rates") if isinstance(g0, dict) else None
            if rates:
                print("rate0:", json.dumps(rates[0], ensure_ascii=False)[:400])


if __name__ == "__main__":
    asyncio.run(main())
