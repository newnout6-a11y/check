# language: python, file: scratch/_debug_schema2.py — полная схема billing_address
import asyncio
import json
import sys

from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://magnesiumshop.nl"
    api = f"{root}/wp-json/wc/store/v1"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.options(f"{api}/checkout", timeout=15)
        d = r.json()
        for ep in d.get("endpoints", []):
            if "POST" in ep.get("methods", []):
                args = ep.get("args", {})
                for name in ("billing_address", "shipping_address"):
                    spec = args.get(name, {})
                    print(f"\n=== {name} ===")
                    for f, meta in (spec.get("properties") or {}).items():
                        req = meta.get("required", False)
                        print(f"  {f:14} required={req} type={meta.get('type')}")
                print("\ntop-level args:", list(args.keys()))


if __name__ == "__main__":
    asyncio.run(main())
