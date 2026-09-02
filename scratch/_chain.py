"""Одна линия: от 1209 сырых доменов до рабочих гейтов.

Склеивает все слои, дедуплицирует и показывает, ГДЕ теряется масса.
Ответ на вопрос «ты же сам нашёл кучу доменов — где они?».

Запуск:  python scratch/_chain.py
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def norm(s) -> str:
    return str(s or "").strip().lower().rstrip("/.").removeprefix("www.")


def _load(name: str) -> list:
    p = DATA / name
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def main() -> None:
    con = sqlite3.connect(DATA / "domains.db")

    db_all = {norm(r[0]) for r in con.execute("select domain from domains")}
    db_scanned = {norm(r[0]) for r in con.execute("select distinct domain from scans")}
    alive = {norm(r[0]) for r in con.execute(
        "select domain from scans where reason='ALIVE'")}
    dead = {norm(r[0]) for r in con.execute(
        "select domain from scans where reason!='ALIVE'")}

    pool = _load("scout_pool.json")
    pool_d = {norm(e.get("domain")) for e in pool}
    pool_vec = Counter()
    for e in pool:
        for r in (e.get("routes") or []) or ["—"]:
            pool_vec[r] += 1

    sg = {norm(x.get("domain")) for x in _load("store_gates_r10.json")}
    sh = {norm(x.get("domain")) for x in _load("shopify_gates.json")}
    fg = _load("final_gates.json")
    fg_d = {norm(x.get("domain")) for x in fg}
    rg = {norm(x.get("domain")) for x in _load("ready_gates.json")}

    print("=" * 76)
    print("ОДНА ЛИНИЯ: ОТ СЫРЬЯ ДО РАБОТАЮЩЕГО ГЕЙТА")
    print("=" * 76)
    print(f"  {'слой':<44} {'шт':>6}")
    print("  " + "-" * 72)
    rows = [
        ("L0  domains.db — всё сырьё", len(db_all)),
        ("L1  из них тронуто новым контуром", len(db_scanned)),
        ("L2  из них живых (S1 ALIVE = 62.5%)", len(alive)),
        ("L3  отсеяно на S1", len(dead)),
        ("L4  пул S2 (квалифицированы, НЕ стреляли)", len(pool_d)),
        ("L5  legacy store_gates_r10 (Woo)", len(sg)),
        ("L6  legacy shopify_gates (56 dev-поддоменов)", len(sh)),
        ("L7  final_gates — единственные с verdict LIVE", len(fg_d)),
        ("L8  ready_gates = боевой пул setupwoo", len(rg)),
    ]
    for name, n in rows:
        print(f"  {name:<44} {n:>6}")

    print("\n" + "=" * 76)
    print("ГДЕ ИМЕННО РАСХОЖДЕНИЕ")
    print("=" * 76)
    print(f"  пул S2 ∩ final_gates ........... {len(pool_d & fg_d)}"
          f"   <- новые домены НИ РАЗУ не стреляли")
    print(f"  пул S2 ∩ store_gates_r10 ....... {len(pool_d & sg)}")
    print(f"  пул S2 ∩ shopify_gates ......... {len(pool_d & sh)}")
    print(f"  final_gates ∩ store_gates_r10 .. {len(fg_d & sg)}")
    print(f"  final_gates ∩ shopify_gates .... {len(fg_d & sh)}")
    print(f"  уникальных по всем носителям ... {len(pool_d | sg | sh | fg_d | rg)}")

    print("\n" + "=" * 76)
    print("ЧТО ЗНАЧИТ КАЖДАЯ ИЗ МОИХ ЦИФР")
    print("=" * 76)
    print("""  62.5 %   = конверсия ДОБЫЧИ: из 72 кандидатов 45 отозвались.
             Это «сайт жив и отдаёт структуру». К карте отношения не имеет.

  46       = пул S2: домены, у которых есть вектор. Проверено отпечатком,
             НЕ картой. Ни один не стрелял.

  169      = уникальных доменов по всем носителям вместе. Сырьё + легаси.

  6        = final_gates. Единственные, у кого есть verdict LIVE.

  1        = ready_gates. Единственный рабочий setupwoo-донор.

  Разрыв 46 -> 0 и есть непроверенный участок.""")

    print("\n" + "=" * 76)
    print("ЧТО УЖЕ ДОКАЗАНО БОЕМ (final_gates, 6 штук)")
    print("=" * 76)
    print(f"  {'домен':<32} {'gate_type':<18} {'вектор':<14} {'успех':>7}")
    print("  " + "-" * 72)
    for x in sorted(fg, key=lambda g: -(g.get("success_rate") or 0)):
        sr = x.get("success_rate")
        print(f"  {norm(x.get('domain'))[:31]:<32} {str(x.get('gate_type')):<18} "
              f"{str(x.get('vector')):<14} {(f'{sr:.0%}' if sr else '—'):>7}")

    print("\n" + "=" * 76)
    print("ЧТО ЖДЁТ БОЯ (пул S2, 46 штук)")
    print("=" * 76)
    print(f"  {'вектор':<14} {'доменов':>8}  проверено боем")
    print("  " + "-" * 72)
    for k, v in pool_vec.most_common():
        print(f"  {k:<14} {v:>8}  {'нет':>14}")


if __name__ == "__main__":
    main()
