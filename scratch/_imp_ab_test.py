# language: Python 3.12+, file: scratch/_imp_ab_test.py
# A/B отпечатка на ЖИВОМ пуле. Ни карт, ни чекаута, ни списаний — только
# достижимость витрины и Store API. Тот же сигнал, что даёт 429, но бесплатно.
#
# Зачем: D-30 (chrome120+ режется Cloudflare429) правлен в gate_client.py и
# остальных живых модулях. Проверить надо на реальном пуле, а не на выдумке,
# но гонять боевые карты по 50 магазинам ради замера — сжигать ресурс зря.
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from curl_cffi.requests import AsyncSession

OLD = "chrome131"
REPEAT = 2          # сколько повторов на режим: сглаживаем случайный 429


async def probe(dom: str, imp: str, sem: asyncio.Semaphore) -> dict:
    root = f"https://{dom}"
    out = {"domain": dom, "imp": imp}
    async with sem:
        try:
            async with AsyncSession(impersonate=imp, verify=False) as s:
                r = await s.get(root, timeout=20)
                out["home"] = r.status_code
                if r.status_code >= 400:
                    return out
                host = r.url.split("//", 1)[-1].split("/", 1)[0]
                r2 = await s.get(f"https://{host}/wp-json/wc/store/v1/cart", timeout=20)
                out["cart"] = r2.status_code
                out["nonce"] = bool(r2.headers.get("nonce") or r2.headers.get("Nonce"))
        except Exception as e:                              # noqa: BLE001
            low = str(e).lower()
            out["err"] = "timeout" if "timeout" in low else type(e).__name__
    return out


def score(rows: list[dict]) -> tuple[int, int, Counter]:
    """Дошли до Store API с nonce = поверхность рабочая."""
    ok = sum(1 for r in rows if r.get("cart") == 200 and r.get("nonce"))
    blocked = sum(1 for r in rows if r.get("home") in (403, 429, 503))
    return ok, blocked, Counter(r.get("home") for r in rows)


async def main():
    path = os.path.join("data", "store_gates.json")
    gates = json.load(open(path, encoding="utf-8"))
    doms = [g["domain"] for g in gates]
    print("=" * 84)
    print(f"[*] A/B отпечатка на {len(doms)} доменах пула (без карт и чекаута)")
    print(f"[*] старый: {OLD} | новый: ротация по config.pick_impersonate()")
    print("=" * 84)

    sem = asyncio.Semaphore(6)
    results = {}
    for mode in ("old", "new"):
        rows = []
        for _ in range(REPEAT):
            imp = OLD if mode == "old" else config.pick_impersonate()
            got = await asyncio.gather(*[probe(d, imp, sem) for d in doms])
            rows.extend(got)
        # по домену берём лучший результат из повторов
        best = {}
        for r in rows:
            d = r["domain"]
            if d not in best or (r.get("cart") == 200 and r.get("nonce")):
                best[d] = r
        results[mode] = list(best.values())
        ok, blocked, codes = score(results[mode])
        print(f"  {mode:4} Store API с nonce: {ok:3}/{len(doms)}   "
              f"заблокировано на витрине: {blocked:3}   коды: {dict(codes)}")

    old_ok, _, _ = score(results["old"])
    new_ok, _, _ = score(results["new"])
    print("-" * 84)
    delta = new_ok - old_ok
    print(f"  Δ = {delta:+d} поверхностей ({old_ok} -> {new_ok})")
    if delta:
        print("  выигранные домены:")
        oldset = {r["domain"] for r in results["old"] if r.get("cart") == 200 and r.get("nonce")}
        for r in results["new"]:
            if (r.get("cart") == 200 and r.get("nonce") and r["domain"] not in oldset):
                print(f"     + {r['domain']:34} imp={r['imp']}")

    out = os.path.join("data", "_imp_ab.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[+] сырые результаты: {out}")


if __name__ == "__main__":
    asyncio.run(main())
