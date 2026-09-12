# language: Python 3.12+, file: scratch/check_20_shopify.py, target: Windows 11
"""Лайв-проверка раздела 3: 20 Shopify-магазинов через модернизированный Shopify-гейт.

Проверяем именно те позиции, которые правили:
  * какая ветка чекаута реально отработала (checkout_one_graphql vs classic_form);
  * каталог искался с пагинацией (config.SHOPIFY_CATALOG_PAGES);
  * вердикт остаётся внутри config.VERDICTS;
  * CAPTCHA/Cloudflare больше не выводится из контейнера легитимного виджета.

    python scratch/check_20_shopify.py [--count 20] [--concurrency 5]
Отчёт: data/results/check20_shopify_<ts>.json
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
import shopify_gate as sg

MAX_PRICE = 2000


def load_targets(limit: int) -> list[str]:
    out = []
    for line in (ROOT / "data" / "shopify_targets.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip("/")
        if not line or line.startswith("#"):
            continue
        if not line.startswith("http"):
            line = "https://" + line
        out.append(line)
        if len(out) >= limit:
            break
    return out


def probe_card() -> str:
    p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    return f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"


async def run_one(target: str, sem: asyncio.Semaphore, results: list) -> None:
    card = probe_card()
    t0 = time.monotonic()
    async with sem:
        try:
            res = await asyncio.wait_for(sg.check_target(target, card, None, MAX_PRICE), timeout=180)
        except Exception as exc:  # noqa: BLE001
            res = {"status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:150]}
    ms = int((time.monotonic() - t0) * 1000)
    status = str(res.get("status", ""))
    flow = str(res.get("flow") or "-")
    rec = {
        "target": target,
        "status": status,
        "flow": flow,
        "handled": status in config.VERDICTS or config.coerce_verdict(status) == "ERROR",
        "coerced": config.coerce_verdict(status),
        "refundable": config.is_refundable(status),
        "detail": str(res.get("detail", ""))[:160],
        "amount_cents": res.get("amount_cents", 0),
        "currency": res.get("currency", ""),
        "variant_id": res.get("variant_id"),
        "latency_ms": ms,
        "card": gc.mask_pan(card),
    }
    results.append(rec)
    mark = "OK " if rec["handled"] else "!!!"
    print(f"{mark} [{status:16}] flow={flow:22} {target[:38]:38} {ms:6}ms {rec['detail'][:52]}", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Лайв-проверка 20 Shopify-магазинов после раздела 3")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    targets = load_targets(args.count)
    print("=" * 104)
    print(f"[*] SHOPIFY ЛАЙВ-ПРОВЕРКА: {len(targets)} магазинов | крышка {MAX_PRICE}c | direct | "
          f"конкурентность {args.concurrency} | каталог до {config.SHOPIFY_CATALOG_PAGES} страниц")
    print("=" * 104, flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []
    await asyncio.gather(*(run_one(t, sem, results) for t in targets))

    by_status = Counter(r["status"] for r in results)
    by_flow = Counter(r["flow"] for r in results)
    clean = [r for r in results if r["status"].startswith(("DECLINED", "APPROVED", "3DS"))
             or r["status"] in ("PI_PENDING", "RATE_LIMITED", "WRONG_CVC", "RESTRICTED", "INVALID", "EXPIRED")]
    unhandled = [r for r in results if not r["handled"]]
    unknown = [r for r in results if r["coerced"] == "UNKNOWN"]
    lat = sorted(r["latency_ms"] for r in results)

    print("\n" + "=" * 104)
    print(f"[*] ИТОГ: {len(results)} | чистых вердиктов процессора: {len(clean)} | "
          f"технических (ERROR, refundable): {len(results) - len(clean)} | UNKNOWN: {len(unknown)} | "
          f"не обработано: {len(unhandled)} | медиана {lat[len(lat)//2]}ms")
    print("[*] Ветки чекаута:", dict(by_flow))
    for st, n in by_status.most_common():
        print(f"    {config.icon(st)} {st:18} {n}")
    if unhandled:
        print("[!] не обработано:")
        for r in unhandled:
            print(f"    {r['target']} -> {r['status']} | {r['detail'][:70]}")

    out = ROOT / "data" / "results"
    out.mkdir(parents=True, exist_ok=True)
    report = out / f"check20_shopify_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(json.dumps({
        "total": len(results), "clean": len(clean), "unhandled": len(unhandled),
        "unknown": len(unknown), "by_status": dict(by_status), "by_flow": dict(by_flow),
        "results": sorted(results, key=lambda r: r["target"]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] Отчёт: {report}")
    return 0 if not unhandled else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
