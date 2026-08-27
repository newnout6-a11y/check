# language: python, file: scratch/_debug_schema.py — Store API checkout schema для NL
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://magnesiumshop.nl"
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # OPTIONS /checkout — REST-схема
        r = await s.options(f"{api}/checkout", timeout=15)
        print("OPTIONS /checkout:", r.status_code)
        try:
            d = r.json()
            props = (((d.get("components") or {}).get("schemas") or {})
                     .get("checkout", {}).get("properties") or {})
            if props:
                print("top-level props:", list(props.keys()))
                addr = props.get("billing_address") or {}
                ref = (addr.get("$ref") or "")
                print("billing_address $ref:", ref)
                # резолвим $ref в schemas
                schemas = (d.get("components") or {}).get("schemas") or {}
                name = ref.split("/")[-1] if ref else ""
                addr_props = (schemas.get(name, {}) or {}).get("properties") or {}
                if addr_props:
                    print("address fields:")
                    for k, v in addr_props.items():
                        print(f"   {k}: {json.dumps(v, ensure_ascii=False)[:140]}")
            else:
                print(json.dumps(d, ensure_ascii=False)[:1500])
        except Exception as e:
            print("no json:", e, r.text[:400])


if __name__ == "__main__":
    asyncio.run(main())
