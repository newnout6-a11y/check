# -*- coding: utf-8 -*-
import asyncio, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_client as gc
from curl_cffi.requests import AsyncSession

async def main():
    # 1) донор напрямую
    t0 = time.perf_counter()
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            r = await s.get("https://www.blackbeltprotein.com.au/my-account/", timeout=12)
            print(f"direct GET донора: {r.status_code}, {int((time.perf_counter()-t0)*1000)}мс, "
                  f"nonce={'yes' if gc.extract_reg_nonce(r.text) else 'NO'}")
    except Exception as e:
        print(f"direct GET донора: FAIL {type(e).__name__}: {str(e)[:120]}")
    # 2) пять случайных прокси из пула к донору
    pool = gc.load_proxies()
    print(f"пул: {len(pool)}")
    import random
    for p in random.sample(pool, min(5, len(pool))):
        t0 = time.perf_counter()
        try:
            async with AsyncSession(impersonate="chrome131", verify=False, proxy=p) as s:
                r = await s.get("https://www.blackbeltprotein.com.au/my-account/", timeout=12)
                print(f"  {p}: {r.status_code}, {int((time.perf_counter()-t0)*1000)}мс")
        except Exception as e:
            print(f"  {p}: FAIL {type(e).__name__} {int((time.perf_counter()-t0)*1000)}мс")

asyncio.run(main())
