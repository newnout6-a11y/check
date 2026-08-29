# language: Python 3.12+, file: scratch/_scan_donation_forms.py, target: Windows 11
# GiveWP/donation lane: формы без регистрации, pk_live прямо на странице.
# Это цели для confirm_gate (PI confirm), не для setup_gate.
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

from curl_cffi.requests import AsyncSession

import domains_store
import gate_client as gc

OUT = Path(__file__).resolve().parents[1] / "data" / "donation_targets.txt"
PATHS = ["/donations/", "/donate/", "/donation/", "/give/", "/support-us/", "/ways-to-give/"]


async def one(dom: str, sem: asyncio.Semaphore):
    async with sem:
        base = f"https://{dom}"
        for path in PATHS:
            try:
                async with AsyncSession(impersonate="chrome131", verify=False) as s:
                    r = await s.get(base + path, timeout=8, allow_redirects=True)
                if r.status_code != 200 or not r.text:
                    continue
                html = r.text
                # GiveWP-маркеры
                if not ("give_" in html or "GiveWP" in html or "give-wp" in html):
                    continue
                pk = gc.extract_pk_live(html)
                mints = gc.detect_secret_mints(html, base + path)
                secrets = gc.extract_client_secrets(html)
                if pk and (mints or secrets or "give_stripe" in html or "give-payment" in html):
                    print(f"  [HIT] {dom}{path} pk={pk[:22]} mints={len(mints)} secs={len(secrets)}")
                    return f"https://{dom}{path}"
            except Exception:
                continue
    return None


async def main():
    rows = domains_store.all_domains()
    doms = [r["domain"] for r in rows]
    print(f"[*] Donation-form scan over {len(doms)} db domains x {len(PATHS)} paths...")
    sem = asyncio.Semaphore(16)
    hits = [h for h in await asyncio.gather(*[one(d, sem) for d in doms]) if h]
    OUT.write_text("\n".join(sorted(set(hits))) + ("\n" if hits else ""), encoding="utf-8")
    print(f"[+] {len(set(hits))} donation targets -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
