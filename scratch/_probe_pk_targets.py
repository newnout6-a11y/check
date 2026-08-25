# language: Python 3.12+, file: scratch/_probe_pk_targets.py, target: Windows 11
# Which store targets expose pk_live on standard paths?
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc

PATHS = ["/", "/checkout/", "/shop/", "/product-category/shop/", "/donations/"]
FILE = Path(__file__).resolve().parents[1] / "data" / "store_targets.txt"


async def main():
    roots = [ln.strip() for ln in FILE.read_text(encoding="utf-8").splitlines()
             if ln.strip().startswith("http")]
    sem = asyncio.Semaphore(6)

    async def one(root: str) -> str:
        async with sem:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                for p in PATHS:
                    try:
                        r = await s.get(root + p, timeout=8)
                        pk = gc.extract_pk_live(r.text) or ""
                    except Exception:
                        continue
                    if pk:
                        print(f"[OK  ] {root} pk={pk[:26]}")
                        return root
            print(f"[MISS] {root}")
            return ""

    results = await asyncio.gather(*[one(r) for r in roots])
    good = sorted(x for x in results if x)
    FILE.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
    print(f"[*] {len(good)}/{len(roots)} targets with pk -> {FILE}")


if __name__ == "__main__":
    asyncio.run(main())
