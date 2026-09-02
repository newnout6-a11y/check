# language: Python 3.12+, file: scout.py, target: Windows 11, deps: curl_cffi
# Раунд 10: оркестратор воронки. S0 (добыча) -> S1 (отпечаток) -> S2 (роутинг)
# -> ранжирование -> пул.
#
# Главное отличие от v1: воронка ЗАМЕРЯЕТСЯ. Каждый кандидат, отсеянный на
# любой стадии, пишет причину из закрытого enum в funnel. Раунд без цифр о
# том, где умирают кандидаты, не считается сделанным — иначе мы правим не то.
import argparse
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import domains_store
import funnel
import recon
import surface

POOL_PATH = os.path.join("data", "scout_pool.json")

# Вес вектора: чем дешевле проверка и выше ценность, тем раньше в очереди.
# setupwoo — $0-авторизация, не сжигает ни цента и не зависит от цены товара.
# storegate — РЕАЛЬНОЕ списание на сумму товара, поэтому последний.
VECTOR_WEIGHT = {"setupwoo": 0, "piconfirm": 1, "braintreenvbv": 2,
                 "shopify": 3, "storegate": 4}


def rank(fp: dict) -> tuple:
    """Ключ сортировки: лучшие первыми. Меньше = лучше."""
    routes = fp.get("routes") or []
    if not routes:
        return (99, 0, 0)
    best = min(VECTOR_WEIGHT.get(r, 9) for r in routes)
    # среди равных векторов — где ключ уже на витрине (не надо идти в /checkout)
    pk_ready = 0 if fp.get("payments", {}).get("stripe_pk") else 1
    # и где товар дешевле (для storegate это деньги)
    cheap = fp.get("cheapest_cents")
    return (best, pk_ready, cheap if isinstance(cheap, int) else 10 ** 9)


def to_pool_entry(fp: dict) -> dict:
    p = fp.get("payments") or {}
    return {
        "domain": fp["domain"],
        "canonical_host": fp.get("canonical_host") or fp["domain"],
        "platform": fp.get("platform"),
        "routes": fp.get("routes") or [],
        "stripe_pk": p.get("stripe_pk") or "",
        "pk_deferred": bool(fp.get("pk_deferred")),
        "card_method": surface._card_method_slug(p.get("methods") or []) or "",
        "methods": p.get("methods") or [],
        "braintree": bool(p.get("braintree")),
        "reg_nonce": bool(p.get("reg_nonce")),
        "reg_nonce_value": p.get("reg_nonce_value") or "",
        "cheapest_cents": fp.get("cheapest_cents"),
        "catalog_size": fp.get("catalog_size"),
        "geo": fp.get("geo") or {},
        "currency": (fp.get("geo") or {}).get("currency") or "",
        "evidence": fp.get("evidence") or [],
        "impersonate": fp.get("impersonate") or "",
        "ms": fp.get("ms"),
    }


async def run(queries: int = 12, delay: float = 5.0, concurrency: int = 16,
              use_corpus: bool = False, extra_file: str | None = None,
              use_db: bool = False, verbose: bool = True,
              reset: bool = False) -> list[dict]:
    funnel.init_db()
    if reset:
        # воронка копится между прогонами; без сброса отчёт показывает смесь
        # нескольких запусков и конверсия перестаёт что-либо значить
        funnel.reset()

    # --- S0: добыча ----------------------------------------------------------
    cands: list[tuple[str, str]] = []
    if queries:
        if verbose:
            print(f"[S0] дорк-полоса: до {queries} запросов, пауза {delay}s")
        got = await recon.lane_dork(max_queries=queries, min_delay=delay,
                                    verbose=verbose)
        print(f"[S0] дорк    : {len(got)} кандидатов")
        cands += got
    if use_corpus:
        got = recon.lane_corpus()
        print(f"[S0] корпус  : {len(got)} кандидатов")
        cands += got
    if extra_file:
        got = recon.lane_file(extra_file)
        print(f"[S0] файл    : {len(got)} кандидатов")
        cands += got
    if use_db:
        got = recon.lane_db_pending()
        print(f"[S0] база    : {len(got)} кандидатов")
        cands += got

    if not cands:
        print("[!] полосы дали ноль кандидатов — нечего квалифицировать")
        return []

    # --- S1 + S2: отпечаток и роутинг ---------------------------------------
    fps = await recon.run(cands, concurrency=concurrency)
    qualified = [fp for fp in fps if fp.get("alive") and fp.get("routes")]
    qualified.sort(key=rank)

    print()
    print("=" * 96)
    print(f"[S2] КВАЛИФИЦИРОВАНО: {len(qualified)} из {len(fps)}")
    print("=" * 96)
    print(f"  {'домен':34} {'векторы':22} {'платформа':12} {'цена':>7} {'ключ':5} гео")
    print("-" * 96)
    for fp in qualified:
        p = fp.get("payments") or {}
        cheap = fp.get("cheapest_cents")
        pk = "pk" if p.get("stripe_pk") else ("отлож" if fp.get("pk_deferred") else "-")
        geo = (fp.get("geo") or {}).get("country") or "?"
        print(f"  {fp['domain']:34} {','.join(fp['routes']):22} "
              f"{fp.get('platform',''):12} {str(cheap if cheap is not None else '-'):>7} "
              f"{pk:5} {geo}")

    print()
    print("  векторы  :", dict(Counter(r for fp in qualified for r in fp["routes"])))
    print("  платформы:", dict(Counter(fp["platform"] for fp in fps if fp.get("alive"))))

    # --- запись --------------------------------------------------------------
    recon.write_back(fps)
    pool = [to_pool_entry(fp) for fp in qualified]
    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    print(f"\n[+] пул записан: {POOL_PATH} ({len(pool)})")

    # setupwoo-кандидаты — отдельно: это закрытый конец A4
    sw = [fp for fp in qualified if "setupwoo" in fp["routes"]]
    if sw:
        print(f"\n[A4] setupwoo-кандидатов ($0-авторизация, открытая регистрация): {len(sw)}")
        for fp in sw:
            g = (fp.get("geo") or {}).get("country") or "?"
            nonce = (fp.get("payments") or {}).get("reg_nonce_value") or ""
            print(f"     {fp['domain']:34} {g:3} nonce={nonce[:10]}")
    return fps


def main():
    ap = argparse.ArgumentParser(description="S0→S2: добыча, отпечаток, роутинг")
    ap.add_argument("--queries", type=int, default=12, help="дорк-запросов")
    ap.add_argument("--delay", type=float, default=5.0, help="пауза между запросами")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--corpus", action="store_true", help="+ майнинг TG-корпуса")
    ap.add_argument("--file", default=None, help="+ файл со списком доменов")
    ap.add_argument("--db", action="store_true", help="+ непросканированное из базы")
    ap.add_argument("--only-report", action="store_true",
                    help="не добывать, только сводка по последнему прогону")
    ap.add_argument("--reset", action="store_true",
                    help="очистить воронку перед прогоном (иначе отчёт — смесь запусков)")
    a = ap.parse_args()

    if a.only_report:
        funnel.init_db()
        print(funnel.report())
        if os.path.exists(POOL_PATH):
            pool = json.load(open(POOL_PATH, encoding="utf-8"))
            print(f"\nпул {POOL_PATH}: {len(pool)} записей")
            print("  векторы:", dict(Counter(r for e in pool for r in e["routes"])))
        return

    asyncio.run(run(queries=a.queries, delay=a.delay, concurrency=a.concurrency,
                    use_corpus=a.corpus, extra_file=a.file, use_db=a.db,
                    reset=a.reset))
    print()
    print(funnel.report())


if __name__ == "__main__":
    main()
