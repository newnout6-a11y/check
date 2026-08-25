# language: Python 3.12+, file: scratch/_probe_mint.py, target: Windows 11
# Diagnose mint endpoints on a target: what do they return on bare POST?
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc

TARGET = sys.argv[1] if len(sys.argv) > 1 else "https://artisalwaysmagic.com/checkout"


async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(TARGET, timeout=15)
        html = r.text
        print(f"[*] GET {TARGET} -> {r.status_code}, {len(html)} bytes")
        pk = gc.extract_pk_live(html)
        secs = gc.extract_client_secrets(html)
        mints = gc.detect_secret_mints(html, TARGET)
        print(f"[*] pk={bool(pk)} secrets={len(secs)} mints={mints}")

        # что вообще есть в странице вокруг payment-intent / clientSecret
        import re
        for kw in ("payment-intent", "paymentIntent", "client_secret", "clientSecret",
                   "wc/store", "cart", "checkout"):
            hits = [m.start() for m in re.finditer(re.escape(kw), html)]
            if hits:
                ctx = html[max(0, hits[0] - 80):hits[0] + 120].replace("\n", " ")
                print(f"  [{kw}] x{len(hits)} | ...{ctx[:180]}...")

        for ep in mints:
            for label, kwargs in (("POST empty", {"data": {}}),
                                  ("POST json {}", {"json": {}})):
                try:
                    rr = await s.post(ep, timeout=10, **kwargs)
                    found = gc.RE_CLIENT_SECRET.findall(rr.text)
                    print(f"[{ep} | {label}] HTTP {rr.status_code} "
                          f"secrets={len(found)} body[:150]={rr.text[:150]!r}")
                except Exception as e:
                    print(f"[{ep} | {label}] EXC {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
