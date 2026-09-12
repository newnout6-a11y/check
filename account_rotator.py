# language: Python 3.12+, file: account_rotator.py, target: Windows 11, deps: curl_cffi
"""Ротация checkout-ссылки аккаунтом: выпуск новой сессии взамен умершей.

Зачем: живой замер 2026-09-13 показал, что у аккаунта ровно ОДНА живая ссылка, и выпуск новой
делает предыдущую недействительной. Значит реакция на смерть сессии — замена на месте, а не пул,
и «долбить до победного» ограничено не сессией, а только нашим запасом новых ссылок.

Ключевое свойство: ротация не зависит ни от браузера, ни от платформы. Ей нужен только токен
аккаунта, и он читается откуда угодно, лишь бы лежал в одном из мест:
  1) файл (по умолчанию config.ACCOUNT_AUTH_PATH, путь можно задать аргументом auth_path);
  2) переменные окружения KIMI_ACCESS_TOKEN / KIMI_MSH_SESSION_ID / KIMI_MSH_DEVICE_ID / KIMI_TRAFFIC_ID.

Формат файла — обычный JSON, достаточно одного поля:
    {"access_token": "eyJhbGciOi..."}
Остальные заголовки подставятся значениями по умолчанию, их можно переопределить полем "headers".
Заполнить можно руками (скопировать access_token из localStorage kimi.ai) или одной командой
node tools/grab_account_auth.cjs — она снимает токен с уже открытого Chrome по CDP.

Проверка без выпуска ссылки:  python account_rotator.py --check
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession

import config

GATEWAY_URL = ("https://www.kimi.ai/apiv2/kimi.gateway.order.v1.SubscriptionService"
               "/CreateSubscription")

# Заголовки, которые SPA шлёт вместе с токеном: значения стабильные, поэтому лежат здесь, а не в файле.
DEFAULT_HEADERS = {
    "connect-protocol-version": "1",
    "x-msh-platform": "web",
    "x-msh-version": "2.2.0",
    "x-language": "ru",
}

ENV_KEYS = {
    "access_token": "KIMI_ACCESS_TOKEN",
    "refresh_token": "KIMI_REFRESH_TOKEN",
    "x-msh-session-id": "KIMI_MSH_SESSION_ID",
    "x-msh-device-id": "KIMI_MSH_DEVICE_ID",
    "x-traffic-id": "KIMI_TRAFFIC_ID",
}


class AccountAuthError(RuntimeError):
    """Нет данных аккаунта или они неполные — ротация невозможна, и об этом надо сказать прямо."""


def token_expiry(token: str) -> int:
    """Момент истечения токена из его же payload. 0 — если не разобрать.

    Подписи здесь не проверяем: это подсказка для человека, а не контроль доступа. Живой замер
    2026-09-13: токен аккаунта живёт считанные минуты, и 401 на ротации выглядел загадочно —
    теперь про истечение говорим заранее и тем же тоном, что и о других отказах.
    """
    try:
        part = str(token).split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(part.encode()).decode("utf-8", "replace"))
        return int(payload.get("exp") or 0)
    except Exception:
        return 0


def _expiry_note(exp: int) -> str:
    if not exp:
        return ""
    left = exp - int(time.time())
    if left <= 0:
        return "токен уже истёк"
    if left < 120:
        return f"токен истекает через {left} с"
    return f"токен живой ещё {left // 60} мин"


REFRESH_URL = ("https://auth.kimi.ai/api/account.gateway.v1.AuthService/RefreshToken")


async def refresh_access_token(auth: dict, proxy: str | None = None, timeout: int = 20) -> dict:
    """Продлевает access_token по refresh_token — без браузера.

    Найдено 2026-09-13 разбором бандла SPA: страница держит токен через Connect-RPC на
    AUTH_API_HOST (= https://auth.kimi.ai), сервис account.gateway.v1.AuthService, метод RefreshToken,
    тело {"refreshToken": ...} (jsonOptions.useProtoFieldName). Живой ответ: 200 и пара
    {accessToken, refreshToken} с новым сроком 15 минут. Все прежние догадки про www.kimi.ai/apiv2
    были неверны именно из-за хоста и имени сервиса.
    """
    rt = str(auth.get("refresh_token") or "")
    if not rt:
        return {"ok": False, "error": ("нет refresh_token: снять заново — node tools/grab_account_auth.cjs "
                                      f"или положи refresh_token в {config.ACCOUNT_AUTH_PATH}")}
    headers = {"content-type": "application/json", "accept": "application/json",
               "connect-protocol-version": "1", "origin": "https://www.kimi.ai",
               "referer": "https://www.kimi.ai/"}
    try:
        async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
            r = await s.post(REFRESH_URL, json={"refreshToken": rt}, headers=headers, timeout=timeout)
    except Exception as e:
        return {"ok": False, "http": 0, "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        data = r.json() or {}
    except Exception:
        data = {}
    access = str(data.get("accessToken") or "")
    if r.status_code != 200 or not access:
        msg = str(data.get("message") or data.get("code") or r.text[:160])
        return {"ok": False, "http": r.status_code, "error": msg[:300]}
    return {"ok": True, "http": r.status_code, "access_token": access,
            "refresh_token": str(data.get("refreshToken") or rt),
            "expires_at": token_expiry(access)}


def save_auth(auth: dict, path: str | None = None) -> str:
    """Пишет токены обратно в файл, чтобы продление жило между запусками."""
    p = Path(path or auth.get("source_path") or config.ACCOUNT_AUTH_PATH)
    payload: dict = {"access_token": auth.get("access_token") or ""}
    if auth.get("refresh_token"):
        payload["refresh_token"] = auth["refresh_token"]
    headers = dict(auth.get("headers") or {})
    if headers:
        payload["headers"] = headers
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(p)


def default_headers() -> dict:
    return dict(DEFAULT_HEADERS)


def auth_hint(path: str | None = None) -> str:
    p = path or config.ACCOUNT_AUTH_PATH
    return (f"нет данных аккаунта для ротации. Положи файл {p} вида "
            '{"access_token": "..."} (токен от kimi.ai) либо задай переменную '
            f"{ENV_KEYS['access_token']}. Снять токен с открытого Chrome: "
            "node tools/grab_account_auth.cjs")


def load_auth(path: str | None = None) -> dict:
    """Данные аккаунта из файла или окружения. Бросает AccountAuthError с понятной подсказкой."""
    p = Path(path or config.ACCOUNT_AUTH_PATH)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise AccountAuthError(f"файл {p} не читается как JSON: {e}") from e
        token = str((raw or {}).get("access_token") or "").strip()
        if not token:
            raise AccountAuthError(f"в файле {p} нет поля access_token. {auth_hint(path)}")
        headers = default_headers()
        headers.update({str(k): str(v) for k, v in ((raw or {}).get("headers") or {}).items()})
        return {"access_token": token, "headers": headers, "source": f"файл {p}",
                "source_path": str(p),
                "refresh_token": str((raw or {}).get("refresh_token") or ""),
                "expires_at": token_expiry(token),
                "refresh_expires_at": token_expiry(str((raw or {}).get("refresh_token") or ""))}

    token = os.environ.get(ENV_KEYS["access_token"], "").strip()
    if not token:
        raise AccountAuthError(auth_hint(path))
    headers = default_headers()
    for header, env_name in ENV_KEYS.items():
        if header == "access_token":
            continue
        val = os.environ.get(env_name, "").strip()
        if val:
            headers[header] = val
    return {"access_token": token, "headers": headers,
            "source": f"окружение {ENV_KEYS['access_token']}",
            "refresh_token": os.environ.get("KIMI_REFRESH_TOKEN", "").strip(),
            "expires_at": token_expiry(token)}


def _tracking_msg(goods_id: str) -> str:
    """Строка аналитики, которую SPA кладёт в подписку; значения повторяют живую страницу."""
    price = "1900" if goods_id == config.ACCOUNT_ROTATION_GOODS_ID else ""
    return ("&enter_method=upgrade_nav&plan_name=basic&action_type=subscribe&renewal_cycle=1"
            f"&goods_currency=USD&goods_price={price}&actual_currency=USD&actual_price={price}")


async def mint_link(auth: dict | None = None, goods_id: str | None = None,
                    proxy: str | None = None, timeout: int = 20) -> dict:
    """Выпускает новую ссылку. Возвращает {ok, link, subscription_id, http, error}.

    Важно: выпуск новой ссылки делает предыдущую недействительной — это замена, а не пул.
    """
    if auth is None:
        auth = load_auth()
    exp = int(auth.get("expires_at") or token_expiry(auth.get("access_token") or ""))
    # Токен живёт 15 минут, поэтому продлеваем его сами, если он на исходе или уже истёк:
    # refresh_token даёт новую пару без браузера (живой замер 2026-09-13).
    if exp and exp - int(time.time()) < 60:
        ref = await refresh_access_token(auth, proxy=proxy)
        if ref.get("ok"):
            print(f"[*] токен продлён автоматически ({_expiry_note(ref['expires_at'])})")
            auth = {**auth, "access_token": ref["access_token"],
                    "refresh_token": ref["refresh_token"], "expires_at": ref["expires_at"],
                    "refresh_expires_at": token_expiry(ref["refresh_token"])}
            # Продление выдаёт и НОВЫЙ refresh_token: если не сохранить, файл останется со старым,
            # и следующий запуск упрётся в «токен протух». Пишем сразу, ошибку записи не роняем.
            try:
                save_auth(auth)
            except Exception as e:
                print(f"[!] продлённый токен не удалось записать: {e}")
        elif exp <= int(time.time()):
            return {"ok": False, "http": 0,
                    "error": (f"токен истёк и продлить не удалось ({ref.get('error')}) — обнови данные: "
                              "node tools/grab_account_auth.cjs")}
    note = _expiry_note(exp)
    if note and exp - int(time.time()) < 120:
        print(f"[!] {note}: обновить можно так — node tools/grab_account_auth.cjs")
    goods = goods_id or config.ACCOUNT_ROTATION_GOODS_ID
    body = {
        "goods_id": goods,
        "subscription_action": "SUBSCRIPTION_ACTION_CREATE",
        "payment_channel": "PAYMENT_CHANNEL_STRIPE",
        "tracking_msg": _tracking_msg(goods),
    }
    headers = {"content-type": "application/json", **auth["headers"],
               "authorization": auth["access_token"]}
    try:
        async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
            r = await s.post(GATEWAY_URL, json=body, headers=headers, timeout=timeout)
    except Exception as e:
        return {"ok": False, "http": 0, "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        data = r.json() or {}
    except Exception:
        data = {}
    if r.status_code in (401, 403) and not auth.get("_retried"):
        # Первая попытка могла уйти с токеном, который истёк между проверкой и запросом.
        ref = await refresh_access_token(auth, proxy=proxy)
        if ref.get("ok"):
            print("[*] сервер сказал 401 — продлил токен и повторяю")
            retry_auth = {**auth, "access_token": ref["access_token"],
                          "refresh_token": ref["refresh_token"],
                          "expires_at": ref["expires_at"], "_retried": True}
            return await mint_link(retry_auth, goods_id=goods, proxy=proxy, timeout=timeout)
    if r.status_code != 200:
        detail = str((data.get("debug") or {}).get("reason") or data.get("code") or r.text[:160])
        if r.status_code in (401, 403) or "unauthenticated" in json.dumps(data, ensure_ascii=False):
            detail = (f"{detail} — токен аккаунта протух. Продлить: python account_rotator.py --refresh, "
                      f"снять заново: node tools/grab_account_auth.cjs")
        return {"ok": False, "http": r.status_code, "error": detail[:300]}
    link = str(data.get("redirectUrl") or "")
    sub = ((data.get("subscription") or {}).get("subscriptionId") or "")
    if not link.startswith("http"):
        return {"ok": False, "http": r.status_code, "subscription_id": sub,
                "error": "в ответе нет redirectUrl — формат ручки изменился"}
    return {"ok": True, "http": r.status_code, "link": link, "subscription_id": sub}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ротация ссылки: выпуск новой сессии аккаунтом")
    ap.add_argument("--auth", default=None, help="файл с данными аккаунта (по умолчанию data/account_auth.json)")
    ap.add_argument("--goods", default=None, help="id товара (по умолчанию месячный Moderato)")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--check", action="store_true", help="только проверить данные аккаунта, без выпуска")
    ap.add_argument("--refresh", action="store_true",
                    help="продлить access_token по refresh_token и записать файл (браузер не нужен)")
    ap.add_argument("--out", default=None,
                    help="записать ПОЛНУЮ ссылку (с #fid) в файл — без фрагмента checkout отвергает её")
    a = ap.parse_args()
    try:
        auth = load_auth(a.auth)
    except AccountAuthError as e:
        print(f"[x] {e}")
        return 2
    print(f"[+] данные аккаунта: {auth['source']}, токен {len(auth['access_token'])} симв."
          + (f", {_expiry_note(int(auth.get('expires_at') or 0))}" if auth.get("expires_at") else ""))
    if auth.get("refresh_expires_at"):
        days = (int(auth["refresh_expires_at"]) - int(time.time())) / 86400
        print(f"[*] refresh_token живой ещё {days:.1f} сут — это и есть срок жизни всей цепочки")
    if a.refresh:
        res = asyncio.run(refresh_access_token(auth, proxy=a.proxy))
        if not res.get("ok"):
            print(f"[x] продлить не удалось (HTTP {res.get('http')}): {res.get('error')}")
            return 4
        auth["access_token"] = res["access_token"]
        auth["refresh_token"] = res["refresh_token"]
        path = save_auth(auth, a.auth)
        print(f"[+] токен продлён, {_expiry_note(res['expires_at'])}, записан в {path}")
        return 0
    if a.check:
        return 0
    res = asyncio.run(mint_link(auth, goods_id=a.goods, proxy=a.proxy))
    if not res.get("ok"):
        print(f"[x] не выпустилось (HTTP {res.get('http')}): {res.get('error')}")
        return 3
    if a.out:
        from pathlib import Path as _P

        _P(a.out).write_text(res["link"] + "\n", encoding="utf-8")
        print(f"[*] полная ссылка (с фрагментом) записана в {a.out}")
    print(f"[+] новая ссылка: {res['link'].split('#')[0]}")
    print(f"[*] подписка: {res.get('subscription_id')}")
    print("[!] Помни: предыдущая ссылка этим выпуском погашена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())