# language: Python 3.12+, file: bot/gates/piconfirm.py, target: Windows 11, deps: curl_cffi
# Sprint 4 gate #2: PaymentIntent confirm через confirm_gate.ConfirmGateSession.
# Цель берётся из PUSTO_PI_TARGET (env) или первой строки data/pi_target.txt.
import asyncio
import os

import gate_client as gc
from confirm_gate import ConfirmGateSession

NAME = "piconfirm"
COST = 2

_lock = asyncio.Lock()
_gs: ConfirmGateSession | None = None


def _target() -> str:
    t = os.environ.get("PUSTO_PI_TARGET", "")
    if not t:
        p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pi_target.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        t = line.strip()
                        break
    return t.rstrip("/")


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


async def _get_session() -> ConfirmGateSession:
    global _gs
    # TTL/смена цели: закэшенная сессия жива, только если цель не поменялась
    if _gs is not None and _gs.s is not None and _gs.target == _target():
        return _gs
    if _gs is not None:
        try:
            await _gs.close()
        except Exception:
            pass
        _gs = None
    target = _target()
    if not target:
        raise RuntimeError("PI target not configured (env PUSTO_PI_TARGET / data/pi_target.txt)")
    proxy_pool = gc.load_proxies()
    gs = ConfirmGateSession(target, proxy=gc.pick_proxy(proxy_pool, None))
    ok, detail = await gs.open()
    if not ok:
        await gs.close()
        raise RuntimeError(f"gate open failed: {detail}")
    _gs = gs
    return gs


async def gate(cc: str, mm: str, yy: str, cvv: str) -> tuple[str, str]:
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")
    async with _lock:
        try:
            gs = await _get_session()
        except RuntimeError as e:
            return ("ERROR", str(e))
        try:
            res = await gs.check_card(raw)
            return (res.get("status", "ERROR"), res.get("detail", "")[:200])
        except Exception as e:
            _gs = None
            return ("ERROR", f"{type(e).__name__}: {e}"[:200])
