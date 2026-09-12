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
                "expires_at": token_expiry(token)}

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
    if exp and exp <= int(time.time()):
        return {"ok": False, "http": 0,
                "error": ("токен аккаунта истёк — обнови данные: node tools/grab_account_auth.cjs "
                          f"или положи новый access_token в {config.ACCOUNT_AUTH_PATH}")}
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
    if r.status_code != 200:
        detail = str((data.get("debug") or {}).get("reason") or data.get("code") or r.text[:160])
        if r.status_code in (401, 403) or "unauthenticated" in json.dumps(data, ensure_ascii=False):
            detail = (f"{detail} — токен аккаунта протух. Обнови данные: "
                      f"{config.ACCOUNT_AUTH_PATH} или node tools/grab_account_auth.cjs")
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
    a = ap.parse_args()
    try:
        auth = load_auth(a.auth)
    except AccountAuthError as e:
        print(f"[x] {e}")
        return 2
    print(f"[+] данные аккаунта: {auth['source']}, токен {len(auth['access_token'])} симв."
          + (f", {_expiry_note(int(auth.get('expires_at') or 0))}" if auth.get("expires_at") else ""))
    if a.check:
        return 0
    res = asyncio.run(mint_link(auth, goods_id=a.goods, proxy=a.proxy))
    if not res.get("ok"):
        print(f"[x] не выпустилось (HTTP {res.get('http')}): {res.get('error')}")
        return 3
    print(f"[+] новая ссылка: {res['link'].split('#')[0]}")
    print(f"[*] подписка: {res.get('subscription_id')}")
    print("[!] Помни: предыдущая ссылка этим выпуском погашена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())