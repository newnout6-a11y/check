# language: Python 3.12+, file: scratch/_build_store_targets.py, target: Windows 11
# Sweep db domains for WooCommerce Store API presence (checkout bootstrap) and
# write confirmed roots to data/store_targets.txt for store_gate / bot gate #3.
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import domains_store

OUT = Path(__file__).resolve().parents[1] / "data" / "store_targets.txt"
PATHS = ["/", "/checkout/", "/shop/"]


async def sweep(domains):
    sem = asyncio.Semaphore(16)
    found = []

    async def one(dom: str):
        async with sem:
            base = f"https://{dom}"
            for path in PATHS:
                try:
                    async with AsyncSession(impersonate="chrome131", verify=False) as s:
                        r = await s.get(base + path, timeout=8)
                    if r.status_code != 200:
                        continue
                    if "wc/store/v1" in r.text or "/wp-json/wc/store/v1" in r.text:
                        print(f"  [STORE] {dom}{path}")
                        found.append(base)
                        break
                except Exception:
                    continue

    await asyncio.gather(*[one(d) for d in domains])
    return found


async def main():
    rows = domains_store.all_domains()
    doms = [r["domain"] for r in rows]
    print(f"[*] Sweeping {len(doms)} domains for Woo Store API surface...")
    hits = await sweep(doms)
    OUT.write_text("\n".join(sorted(set(hits))) + ("\n" if hits else ""), encoding="utf-8")
    print(f"[+] {len(set(hits))} store targets -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
