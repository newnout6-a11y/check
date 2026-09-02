"""Перепись по СЕРВИСАМ, а не по сайтам.

Сколько штук каждого платёжного сервиса и платформы есть на всех носителях.
Сводит разрозненные сигналы (pk_live, slug метода, gate_type, platform) к имени
провайдера. Офлайн, без HTTP.

Запуск:  python scratch/_services.py
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Сводка slug-ов методов и gate_type к имени сервиса.
# Ключ — подстрока slug-а в нижнем регистре.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Stripe (напрямую)", ("stripe", "fkwcs")),
    ("WooCommerce Payments", ("woocommerce_payments",)),
    ("PayPal / Braintree", ("paypal", "ppcp")),
    ("Authorize.net", ("authorize_net", "authnet")),
    ("Bambora", ("bambora",)),
    ("Maksekeskus", ("makecommerce",)),
    ("Amazon Pay", ("amazon_payments",)),
    ("Klarna", ("klarna",)),
    ("Affirm", ("affirm",)),
    ("Google Pay", ("googlepay",)),
    ("Apple Pay", ("applepay",)),
    ("Прямой банковский перевод", ("bacs",)),
    ("Наложенный платёж", ("cod",)),
    ("Чек / счет", ("cheque", "invoice")),
]


def classify(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not s:
        return ""
    for name, keys in RULES:
        if any(k in s for k in keys):
            return name
    return f"прочее: {s}"


def _load(name: str):
    p = DATA / name
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def line(name: str, n: int, total: int, note: str = "") -> None:
    bar = "#" * min(n, 40)
    print(f"  {name:<26} {n:>4}  {n / total * 100:>5.1f}%  {bar:<40} {note}")


def head(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main() -> None:
    pool = _load("scout_pool.json")
    sg = _load("store_gates_r10.json")
    sh = _load("shopify_gates.json")
    fg = _load("final_gates.json")

    head("1. ПЛАТФОРМА — СКОЛЬКО КАЖДОЙ")

    plat = Counter()
    for e in pool:
        plat[e.get("platform") or "?"] += 1
    for _ in sh:
        plat["shopify"] += 1
    for _ in sg:
        plat["wordpress + woo"] += 1
    print(f"  {'платформа':<26} {'шт':>4}  доля")
    print("  " + "-" * 74)
    tot = sum(plat.values())
    for k, v in plat.most_common():
        line(k, v, tot)

    head("2. СТРАЙП — СКОЛЬКО СТРАЙПА")
    print("\n  Пул S2 (46 доменов, новых):")
    pk = sum(1 for e in pool if e.get("stripe_pk"))
    cm = Counter(classify(e.get("card_method")) for e in pool if e.get("card_method"))
    print(f"      pk_live на витрине .............. {pk:>3}")
    print(f"      card-метод stripe ............... {cm.get('Stripe (напрямую)', 0):>3}")
    print(f"      card-метод woo payments ......... {cm.get('WooCommerce Payments', 0):>3}")
    print(f"      остальные card-методы ........... {sum(v for k, v in cm.items() if 'Stripe' not in k and 'WooCommerce' not in k):>3}")
    print(f"      pk_deferred (pk возьмём на чекауте) {sum(1 for e in pool if e.get('pk_deferred')):>3}")

    print("\n  store_gates_r10 (50 доменов, Woo Store API):")
    pk_sg = [x for x in sg if x.get("pk_live")]
    print(f"      записей с pk_live ............... {len(pk_sg):>3} из {len(sg)}")
    uniq = Counter(x.get("pk_live") for x in pk_sg)
    print(f"      уникальных Stripe-аккаунтов ..... {len(uniq):>3}")
    dup = {k: v for k, v in uniq.items() if v > 1}
    if dup:
        print(f"\n      ВНИМАНИЕ — один аккаунт на несколько витрин ({len(dup)} ключей):")
        for k, v in sorted(dup.items(), key=lambda kv: -kv[1]):
            doms = [x.get("domain") for x in sg if x.get("pk_live") == k]
            print(f"        {v} витрин на {str(k)[:22]}…")
            print(f"          {', '.join(str(d) for d in doms)}")

    print("\n  shopify_gates (72 записи):")
    print(f"      Shopify Payments (Stripe под капотом) .. {len(sh):>3}")
    print(f"      из них dev-поддомены *.myshopify.com ... {sum(1 for x in sh if 'myshopify.com' in str(x.get('domain',''))):>3}")

    print("\n  final_gates (6 записей):")
    print(f"      с pk_live ....................... {sum(1 for x in fg if x.get('pk_live')):>3} из {len(fg)}")
    print(f"      gate_type wc_stripe_upe ......... {sum(1 for x in fg if x.get('gate_type') == 'wc_stripe_upe'):>3}")

    head("3. ВСЕ ПЛАТЁЖНЫЕ СЕРВИСЫ — СВОДКА ПО ВСЕМ НОСИТЕЛЯМ")

    svc: Counter[str] = Counter()
    where: dict[str, set[str]] = defaultdict(set)

    for e in pool:
        dom = str(e.get("domain"))
        if (e.get("platform") or "").startswith("shopify"):
            svc["Shopify Payments"] += 1
            where["Shopify Payments"].add(dom)
        for m in (e.get("methods") or []):
            c = classify(m)
            if c and not c.startswith("прочее"):
                key = m
                svc[c] += 1
                where[c].add(dom)
        if e.get("stripe_pk"):
            svc["Stripe (pk на витрине)"] += 1
            where["Stripe (pk на витрине)"].add(dom)

    for x in sg:
        if x.get("pk_live"):
            svc["Stripe (Woo Store API)"] += 1
            where["Stripe (Woo Store API)"].add(str(x.get("domain")))
    for x in sh:
        svc["Shopify Payments"] += 1
        where["Shopify Payments"].add(str(x.get("domain")))
    for x in fg:
        if x.get("pk_live"):
            svc["Stripe (final_gates)"] += 1
            where["Stripe (final_gates)"].add(str(x.get("domain")))

    print(f"  {'сервис':<28} {'шт':>4}  {'уник. доменов':>13}")
    print("  " + "-" * 74)
    for k, v in svc.most_common():
        print(f"  {k:<28} {v:>4}  {len(where[k]):>13}")
    print("  " + "-" * 74)
    print(f"  {'ИТОГО слотов':<28} {sum(svc.values()):>4}")

    head("4. СТРАЙП-СЕМЕЙСТВО — ОДНОЙ ЦИФРОЙ")
    fam = (svc.get("Stripe (Woo Store API)", 0)
           + svc.get("Stripe (final_gates)", 0)
           + svc.get("Stripe (pk на витрине)", 0)
           + svc.get("WooCommerce Payments", 0))
    allstripe = (where["Stripe (Woo Store API)"] | where["Stripe (final_gates)"]
                 | where["Stripe (pk на витрине)"] | where["WooCommerce Payments"])
    print(f"  Woo Store API, pk_live ....... {svc.get('Stripe (Woo Store API)', 0):>4}")
    print(f"  final_gates, pk_live ......... {svc.get('Stripe (final_gates)', 0):>4}")
    print(f"  пул S2, pk на витрине ........ {svc.get('Stripe (pk на витрине)', 0):>4}")
    print(f"  пул S2, WooCommerce Payments . {svc.get('WooCommerce Payments', 0):>4}")
    print("  " + "-" * 40)
    print(f"  ИТОГО Stripe-семейство ....... {fam:>4} слотов")
    print(f"  уникальных доменов ........... {len(allstripe):>4}")
    print(f"\n  Сверх того: Shopify Payments = {svc.get('Shopify Payments', 0)} "
          f"(тоже Stripe под капотом, но другой чекаут).")

    head("5. МЕТОДЫ ОПЛАТЫ ПУЛА S2 — ВСЕ SLUG-И")
    mc = Counter()
    for e in pool:
        for m in (e.get("methods") or []):
            mc[m] += 1
    for k, v in mc.most_common():
        print(f"  {k:<34} {v:>3}   -> {classify(k)}")

    head("6. ЧЕМ ЭТО ЗАКАНЧИВАЕТСЯ ДЛЯ БОЯ")
    print(f"  {'вектор':<14} {'целей':>6}  сервис")
    print("  " + "-" * 60)
    print(f"  {'setupwoo':<14} {sum(1 for e in pool if 'setupwoo' in (e.get('routes') or [])):>6}  Stripe / Woo Payments, $0-авторизация")
    print(f"  {'storegate':<14} {sum(1 for e in pool if 'storegate' in (e.get('routes') or [])):>6}  Stripe / Woo Payments, реальное списание")
    print(f"  {'shopify':<14} {sum(1 for e in pool if 'shopify' in (e.get('routes') or [])):>6}  Shopify Payments, реальное списание")
    print(f"  {'legacy woo':<14} {len(pk_sg):>6}  Stripe, Woo Store API (ERROR 35 из 50)")
    print(f"  {'braintreenvbv':<14} {0:>6}  целей нет")
    print(f"  {'piconfirm':<14} {0:>6}  целей нет")


if __name__ == "__main__":
    main()
