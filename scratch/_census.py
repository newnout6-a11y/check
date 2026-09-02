"""Перепись: сколько штук каждого сервиса есть.

Не верит документам и памяти — снимает всё с живых носителей:
  data/scout_pool.json      S2-пул (квалифицированные поверхности)
  data/domains.db           таблицы domains / scans
  data/store_gates_r10.json Woo Store API, раунд 10
  data/shopify_gates.json   Shopify
  data/final_gates.json     рабочий пул: 6 гейтов, все READY/LIVE (НЕ мёртвый)
  data/ready_gates.json     боевой пул setupwoo, читает setup_gate.load_ready_gates()

Запуск:  python scratch/_census.py
Всё офлайн, никакого HTTP.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name: str):
    p = DATA / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _table(rows: list[tuple[str, object]], title: str, note: str = "") -> None:
    if not rows:
        return
    w0 = max(len(str(r[0])) for r in rows)
    w0 = max(w0, len(title))
    print(f"\n{title}" + (f"  ({note})" if note else ""))
    print("  " + "-" * (w0 + 14))
    print(f"  {title:<{w0}}  {'шт':>4}  {'доля':>7}")
    print("  " + "-" * (w0 + 14))
    total = sum(int(r[1]) for r in rows) or 1
    for k, v in rows:
        v = int(v)
        print(f"  {str(k):<{w0}}  {v:>4}  {v / total * 100:>6.1f}%")
    print("  " + "-" * (w0 + 14))
    print(f"  {'ИТОГО':<{w0}}  {sum(int(r[1]) for r in rows):>4}")


def sec(t: str) -> None:
    print("\n" + "=" * 62)
    print(t)
    print("=" * 62)


def main() -> None:
    pool = _load("scout_pool.json") or []

    sec("1. ПУЛ S2 — ПЛАТФОРМА (что это за сайт)")
    _table(Counter(e.get("platform") or "?" for e in pool).most_common(),
           "платформа", f"{len(pool)} доменов")

    sec("2. ПУЛ S2 — ВЕКТОР (чем можно бить)")
    routes = Counter()
    for e in pool:
        for r in (e.get("routes") or []) or ["— нет вектора —"]:
            routes[r] += 1
    _table(routes.most_common(), "вектор", "домен может нести несколько")

    sec("3. ПУЛ S2 — ПЛАТЁЖНЫЙ СТЕК")
    pk = sum(1 for e in pool if e.get("stripe_pk"))
    bt = sum(1 for e in pool if e.get("braintree"))
    rn = sum(1 for e in pool if e.get("reg_nonce"))
    cm = sum(1 for e in pool if e.get("card_method"))
    print(f"  stripe pk на витрине .......... {pk:>4} из {len(pool)}")
    print(f"  braintree ..................... {bt:>4} из {len(pool)}")
    print(f"  reg-nonce (открытая регистрация) {rn:>4} из {len(pool)}")
    print(f"  card-метод в списке методов ... {cm:>4} из {len(pool)}")

    sec("4. ПУЛ S2 — МЕТОДЫ ОПЛАТЫ (slug, как их отдаёт магазин)")
    methods = Counter()
    for e in pool:
        for m in (e.get("methods") or []):
            methods[m] += 1
    _table(methods.most_common(14), "метод", "топ-14")

    sec("5. ПУЛ S2 — ГЕО И ЦЕНА")
    geo = Counter((e.get("geo") or {}).get("country") or "?" for e in pool)
    _table(geo.most_common(), "страна")
    caps = [e.get("cheapest_cents") for e in pool if e.get("cheapest_cents") is not None]
    if caps:
        caps.sort()
        under = sum(1 for c in caps if c <= 2000)
        print(f"\n  цена самого дешёвого товара: {len(caps)} доменов")
        print(f"  медиана ................ {caps[len(caps) // 2] / 100:>8.2f}")
        print(f"  мин / макс ............. {caps[0] / 100:>8.2f} / {caps[-1] / 100:.2f}")
        print(f"  под крышкой $20 ........ {under:>8} ({under / len(caps) * 100:.0f}%)")

    sec("6. БАЗА ДОМЕНОВ — ОТКУДА ПРИШЛИ")
    con = sqlite3.connect(DATA / "domains.db")
    _table(con.execute("select source, count(*) from domains group by 1 order by 2 desc").fetchall(),
           "источник")
    sec("7. БАЗА ДОМЕНОВ — РЕЗУЛЬТАТ СКАНА")
    _table(con.execute("select coalesce(scan_result,'(не сканирован)'), count(*) "
                       "from domains group by 1 order by 2 desc").fetchall(),
           "scan_result")

    sec("8. ВОРОНКА — ПОТЕРИ ПО ПРИЧИНАМ")
    _table(con.execute("select stage || ' / ' || reason, count(*) from scans "
                       "group by 1 order by 2 desc").fetchall(),
           "ступень / причина")

    sec("9. LEGACY-НОСИТЕЛИ (живое против мёртвого)")
    for name, key in (("store_gates_r10.json", "gate_type"),
                      ("shopify_gates.json", None),
                      ("final_gates.json", "gate_type"),
                      ("ready_gates.json", "gate_type")):
        d = _load(name)
        if not d:
            print(f"\n  {name}: нет файла")
            continue
        print(f"\n  {name}: {len(d)} записей")
        if key:
            for k, v in Counter(x.get(key) or "?" for x in d).most_common():
                print(f"      {k:<28} {v:>4}")
        ver = Counter(str(x.get("verified")) for x in d if "verified" in x)
        if ver:
            print(f"      verified: {dict(ver)}")
        for f in ("r10_verified", "r10_status"):
            c = Counter(str(x.get(f)) for x in d if f in x)
            if c:
                print(f"      {f}: {dict(c)}")

    sec("10. ПОДТВЕРЖДЕНИЕ: СКОЛЬКО КАЖДОГО СЕРВИСА ДЛЯ БОЯ")
    print(f"  {'вектор':<16} {'целей':>6}  {'деньги':<34} статус")
    print("  " + "-" * 74)
    plan = [
        ("setupwoo", rn, "$0-авторизация", "готов, не проверен боем"),
        ("storegate", routes.get("storegate", 0), "реальное списание, крышка $20", "готов, не проверен боем"),
        ("shopify", routes.get("shopify", 0), "реальное списание", "есть legacy-прогон"),
        ("braintreenvbv", bt, "—", "D-5: целей нет"),
        ("piconfirm", 0, "—", "D-4: целей нет"),
    ]
    for v, n, money, st in plan:
        print(f"  {v:<16} {n:>6}  {money:<34} {st}")
    print("  " + "-" * 74)


if __name__ == "__main__":
    main()
