# language: Python 3.12+, file: radar_config.py, target: Windows 11, deps: curl_cffi
"""Как настроен Radar и его капча у КОНКРЕТНОЙ ссылки — без траты попытки.

Зачем: на один и тот же наш запрос челлендж приходит на одной сессии и не приходит на другой
(2026-09-18: Kimi проходит до эмитента, Meshy упирается в hCaptcha). Прежде чем жечь попытки,
конфигурация снимается чтением:

  * флаги витрины (checkout_passive_captcha, checkout_enable_link_api_passive_hcaptcha, …);
  * sitekey пассивного контура из link_settings и из wallet-config;
  * ответ hCaptcha checksiteconfig: pass (пассивный проход разрешён или нет), c.type, длина req;
  * история челленджей из data/radar_challenges.jsonl — что именно требовал интерактивный шаг.

Живой замер 2026-09-18 (обе ссылки): флаги и sitekey одинаковые, checksiteconfig отвечает
pass=true, c.type=hsw, enc_get_req=true, req ~736 символов. Настоящий токен (~3.8 КБ, P1_<JWT>)
выпускает только виджет hCaptcha — checksiteconfig/getcaptcha отдают лишь входные req-токены.

CLI:
    python radar_config.py <cs_live-ссылка> [--json]
    python radar_config.py --history
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

import config
import gate_client as gc
import hit_gate
import stripe_salt
from curl_cffi.requests import AsyncSession

# Флаги витрины, которые говорят про капчу (живой ответ 2026-09-18).
CAPTCHA_FLAGS = (
    "checkout_passive_captcha",
    "checkout_enable_link_api_passive_hcaptcha",
    "checkout_enable_link_api_hcaptcha_rqdata",
    "checkout_hcaptcha_redundancy_treatment_1_enabled",
    "checkout_enable_hcaptcha_async_token_logging",
)


def mask(secret: str, keep: int = 8) -> str:
    """Секрет в отчёт: остаётся только начало. rqdata и токены в вывод не попадают."""
    s = str(secret or "")
    return s[:keep] + "…" if len(s) > keep else s


def radar_verdict(rep: dict) -> str:
    """Человеческий вывод по конфигурации: что нас ждёт на этой сессии."""
    if not rep.get("ok"):
        return f"ссылка не читается: {rep.get('detail', '—')}"
    cs_cfg = rep.get("checksiteconfig") or {}
    flags = rep.get("feature_flags") or {}
    passive = flags.get("checkout_passive_captcha")
    if not cs_cfg:
        head = "hCaptcha не отвечает — конфигурацию капчи определить не удалось"
    elif cs_cfg.get("pass") is True:
        head = ("пассивный проход разрешён (pass=true, тип hsw) — виджет решает без картинок, "
                "но токен всё равно выпускает только он")
    else:
        head = "пассивного прохода нет (pass=false) — на этой сессии потребуется интерактивный челлендж"
    tail = ("флаг checkout_passive_captcha включён" if passive
            else "флаг checkout_passive_captcha выключен")
    hist = rep.get("challenges_seen") or []
    hist_line = (f"челлендж уже видели {len(hist)} раз(а), последний sitekey={mask(hist[-1].get('site_key', ''))}"
                 if hist else "челленджей на этой сессии не записано")
    return f"{head}; {tail}; {hist_line}"


def challenges_for(cs: str) -> list[dict]:
    """История челленджей по сессии из журнала (пишет hit_gate.record_radar_challenge)."""
    p = pathlib.Path(getattr(config, "RADAR_CHALLENGE_LOG", "data/radar_challenges.jsonl"))
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if not cs or rec.get("cs") == cs:
                out.append(rec)
    except (OSError, ValueError):
        pass
    return out


async def probe(link: str, proxy: str | None = None, timeout: int = 15) -> dict:
    """Снять конфигурацию капчи у ссылки. Ни одного confirm — попытки не тратятся."""
    pk, cs = hit_gate.extract_session_and_key(link)
    rep: dict = {"link": str(link).split("#")[0], "cs": cs, "ok": False, "detail": ""}
    if not pk.startswith("pk_live") or not cs.startswith("cs_"):
        rep["detail"] = "не разобрать pk/cs из ссылки"
        return rep
    try:
        async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
            r = await s.get(
                f"https://api.stripe.com/v1/payment_pages/{cs}",
                params={"key": pk},
                headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/",
                         "Accept": "application/json"},
                timeout=timeout,
            )
            if r.status_code != 200:
                rep["detail"] = f"payment_pages HTTP {r.status_code}"
                return rep
            data = r.json() or {}
            app = data.get("account_settings") or {}
            rep.update({
                "ok": True,
                "merchant": str((data.get("account") or {}).get("display_name") or app.get("business_name") or ""),
                "currency": str(data.get("currency") or "").upper(),
                "amount_due": hit_gate.presentment_amount(data),
                "session_status": str(data.get("status") or ""),
                "feature_flags": {k: (data.get("feature_flags") or {}).get(k) for k in CAPTCHA_FLAGS},
                "passive_site_key": str((data.get("link_settings") or {}).get("hcaptcha_site_key") or ""),
                "session_rqdata": mask(str((data.get("link_settings") or {}).get("hcaptcha_rqdata") or ""), 10),
            })

            # wallet-config отдаёт второй sitekey — «passive_captcha» карточного элемента.
            try:
                rw = await s.post(
                    "https://merchant-ui-api.stripe.com/elements/wallet-config",
                    data={"stripe_js_id": "00000000-0000-4000-8000-000000000000",
                          "referrer_host": "checkout.stripe.com", "key": pk,
                          "request_surface": "web_split_card_element_popup"},
                    headers={"Origin": "https://js.stripe.com", "Referer": "https://checkout.stripe.com/",
                             "Accept": "application/json"},
                    timeout=timeout,
                )
                wj = rw.json() if rw.status_code == 200 else {}
                rep["wallet_site_key"] = str(gc._find_key(wj, "link_hcaptcha_site_key") or "")
                rep["element_passive_site_key"] = str(gc._find_key(wj, "site_key") or "")
            except Exception as e:
                rep["wallet_error"] = type(e).__name__

            # checksiteconfig: pass/type/req по пассивному sitekey сессии.
            sk = rep.get("passive_site_key") or rep.get("wallet_site_key") or ""
            if sk:
                try:
                    rc = await s.post(
                        "https://api.hcaptcha.com/checksiteconfig",
                        params={"v": stripe_salt.current_salt(), "sitekey": sk, "host": "b.stripecdn.com",
                                "sc": "1", "swa": "1"},
                        headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/",
                                 "Accept": "application/json"},
                        timeout=timeout,
                    )
                    cj = rc.json() if rc.status_code == 200 else {}
                    req = str(gc._find_key(cj, "req") or "")
                    rep["checksiteconfig"] = {
                        "http": rc.status_code,
                        "pass": cj.get("pass"),
                        "type": str((cj.get("c") or {}).get("type") or ""),
                        "req_len": len(req),
                        "features": sorted((cj.get("features") or {}).keys()),
                    }
                except Exception as e:
                    rep["checksiteconfig"] = {"error": type(e).__name__}
    except Exception as e:
        rep["detail"] = f"{type(e).__name__}: {e}"
        return rep

    rep["challenges_seen"] = challenges_for(cs)
    rep["verdict"] = radar_verdict(rep)
    return rep


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Конфигурация Radar и капчи по ссылке чекаута")
    ap.add_argument("link", nargs="?", help="ссылка cs_live…#fid")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    ap.add_argument("--history", action="store_true", help="журнал челленджей без запроса")
    args = ap.parse_args(argv)

    if args.history:
        recs = challenges_for("")
        if not recs:
            print("журнал пуст")
            return 0
        for rec in recs[-20:]:
            print(f"{rec.get('at')} | {rec.get('cs', '')[:24]}… | sitekey={mask(rec.get('site_key', ''))} "
                  f"| rqdata={rec.get('rqdata_len')} | {rec.get('verification_url', '')[:48]}")
        return 0

    if not args.link:
        ap.print_help()
        return 2
    rep = asyncio.run(probe(args.link, proxy=args.proxy))
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep.get("ok") else 1
    if not rep.get("ok"):
        print(f"[x] {rep.get('detail')}")
        return 1
    print(f"[*] {rep.get('merchant') or '—'} | {rep.get('currency')} "
          f"{hit_gate.money(rep.get('amount_due'), rep.get('currency'))} | сессия {rep.get('session_status')}")
    print(f"[*] sitekey пассивного контура витрины: {mask(rep.get('passive_site_key', ''))}")
    print(f"[*] sitekey карточного элемента: {mask(rep.get('element_passive_site_key', ''))}")
    cs_cfg = rep.get("checksiteconfig") or {}
    print(f"[*] checksiteconfig: pass={cs_cfg.get('pass')} type={cs_cfg.get('type')} "
          f"req={cs_cfg.get('req_len')} симв. features={cs_cfg.get('features')}")
    flags = rep.get("feature_flags") or {}
    on = [k for k, v in flags.items() if v]
    print(f"[*] флаги капчи включены: {', '.join(on) if on else '—'}")
    print(f"[=] {rep.get('verdict')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
