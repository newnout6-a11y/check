# language: Python 3.12+, file: tests/test_stripe_section2.py, target: Windows 11
"""Регрессии второго раздела аудита 2026-09 (Stripe-контур).

Проверяют контракт, а не замороженные значения:
* соль stripe.js — формат + наличие скрипта актуализации (значение ротируется);
* самолечение недокументированной телеметрии при 400 parameter_unknown;
* различение «маршрут выведен» (404 на непубличном пути) от отказа карты;
* технические исходы челленджа коэрсятся в ERROR и возвращают кредит;
* состояние сессии /hit не подменяет таксономию вердиктов.
"""
from __future__ import annotations

import asyncio
import pathlib
import re

import pytest

import config
import gate_client as gc

ROOT = pathlib.Path(__file__).resolve().parent.parent
TECHNICAL = ("CHALLENGE_FAILED", "CHALLENGE_BURNED")


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _Session:
    """Отдаёт ответы по очереди и запоминает тела запросов."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.bodies = []

    async def post(self, url, data=None, headers=None, timeout=None):
        self.bodies.append(dict(data or {}))
        return self._responses.pop(0)


def test_salt_is_format_and_refresh_tool_exists():
    """Соль — 10 hex, а не конкретное значение; актуализация живёт в скрипте."""
    assert re.fullmatch(r"[0-9a-f]{10}", config.STRIPE_JS_BUILD), config.STRIPE_JS_BUILD
    assert (ROOT / "scratch" / "refresh_stripe_salt.py").is_file()


def test_tokenize_helper_drops_undocumented_param_and_retries():
    """400 parameter_unknown с именем параметра -> параметр убирается, запрос повторяется."""
    sess = _Session([
        _Resp(400, {"error": {"code": "parameter_unknown",
                              "param": "client_attribution_metadata[payment_intent_creation_flow]",
                              "message": "Received unknown parameter"}}),
        _Resp(200, {"id": "pm_test_1"}),
    ])
    body = {"key": "pk_test_x", "card[number]": "4111111111111111",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred"}
    out = asyncio.run(gc.tokenize_payment_method(sess, body, label="test"))
    assert out["id"] == "pm_test_1"
    assert len(sess.bodies) == 2, "ожидался один повтор после отказа"
    assert "client_attribution_metadata[payment_intent_creation_flow]" not in sess.bodies[1]
    assert sess.bodies[1]["card[number]"] == "4111111111111111", "остальное тело должно уцелеть"
    assert body.get("client_attribution_metadata[payment_intent_creation_flow]") == "deferred", "исходное тело мутировать нельзя"


def test_tokenize_helper_parses_param_from_message():
    """Если Stripe не вернул error.param, имя вытаскивается из текста ошибки."""
    sess = _Session([
        _Resp(400, {"error": {"code": "parameter_unknown",
                              "message": "Received unknown parameter: pasted_fields"}}),
        _Resp(200, {"id": "pm_test_2"}),
    ])
    out = asyncio.run(gc.tokenize_payment_method(sess, {"key": "pk", "pasted_fields": "number,cvc"}, label="test"))
    assert out["id"] == "pm_test_2"
    assert "pasted_fields" not in sess.bodies[1]


def test_tokenize_helper_returns_error_without_unknown_param():
    """Отказ карты (не parameter_unknown) не должен ретраиться и не должен теряться."""
    sess = _Session([_Resp(402, {"error": {"code": "card_declined", "message": "Your card was declined."}})])
    out = asyncio.run(gc.tokenize_payment_method(sess, {"key": "pk"}, label="test"))
    assert out["error"]["code"] == "card_declined"
    assert len(sess.bodies) == 1


ROUTE_GONE = {"error": {"code": "invalid_request_error",
                       "message": "Unrecognized request URL (GET: /v1/payment_pages/)."}}
RESOURCE_MISSING = {"error": {"code": "resource_missing",
                              "message": "No such checkout session: cs_live_probe"}}


def test_internal_endpoint_gone_is_flagged_only_for_internal_paths():
    """404 на непубличном маршруте — сигнал развала контура; 404 на обычном — нет."""
    internal = "https://api.stripe.com/v1/payment_intents/pi_1/verify_challenge"
    assert gc.flag_internal_endpoint(_Resp(404, ROUTE_GONE), internal) is True
    assert gc.flag_internal_endpoint(_Resp(404, ROUTE_GONE),
                                     "https://api.stripe.com/v1/payment_methods") is False
    assert gc.flag_internal_endpoint(_Resp(401, {}), internal) is False


def test_route_404_is_distinguished_from_dead_resource():
    """Живой замер 2026-09-12: роут-404 и ресурс-404 надо различать, иначе алерт станет шумом.

    GET /v1/payment_pages/ и GET /v1/confirmation_tokens отдают «Unrecognized request URL» —
    это выведенный маршрут. GET /v1/payment_pages/cs_live_bogus с валидным pk_live отдаёт
    resource_missing — это мёртвая цель, а не развал контура (в пуле /hit мёртвых целей много).
    """
    internal = "https://api.stripe.com/v1/payment_pages/cs_live_x"
    assert gc.flag_internal_endpoint(_Resp(404, RESOURCE_MISSING), internal) is False
    assert gc.flag_internal_endpoint(_Resp(404, ROUTE_GONE), internal) is True
    # 404 без доказательств роут-отказа (пустой ответ) алертом не считается
    assert gc.flag_internal_endpoint(_Resp(404, {}), internal) is False
    # HTML-страница «Page not found» на внутреннем пути — тоже выведенный маршрут
    # (так отвечает hooks.stripe.com; сам мёртвый /3ds2/fingerprint/complete в маркеры не входит,
    # потому что контур на него больше не ходит — см. config.THREE_DS_METHOD_NOTIFICATION_URL).
    html = _Resp(404, "not json")
    html.text = "<html><head><title>Stripe: Page not found</title></head></html>"
    assert gc.flag_internal_endpoint(html, "https://api.stripe.com/v1/payment_pages/") is True


def test_technical_challenge_statuses_are_known_error_and_refundable():
    for st in TECHNICAL:
        assert st in config.VERDICTS, f"{st} должен быть в таксономии"
        assert st in config.VERDICT_ICONS, f"{st} без иконки"
        assert config.coerce_verdict(st) == "ERROR"
        assert config.is_refundable(st) is True


def test_legacy_hit_statuses_do_not_escape_taxonomy():
    """INVALID_URL/EXCEPTION/FAILED больше не уходят в UNKNOWN (аудит 2026-09, G-10)."""
    for st in ("INVALID_URL", "EXCEPTION", "FAILED"):
        assert config.coerce_verdict(st) == "ERROR"
    assert "COMPLETED" not in config.VERDICTS and "SUCCESS" not in config.VERDICTS
    assert "SUCCESS" in config.PIPELINE_STATES and "COMPLETED" in config.PIPELINE_STATES


def test_undocumented_endpoints_registry_is_descriptive():
    assert config.UNDOCUMENTED_ENDPOINTS, "реестр непубличных маршрутов не должен быть пустым"
    for path, note in config.UNDOCUMENTED_ENDPOINTS.items():
        assert path.startswith("/v1/"), path
        assert note.strip(), f"у {path} нет пояснения"


def test_hit_gate_separates_session_state_from_verdicts():
    """qualify_session отдаёт session_status, execute_hit — status-таксономию и pipeline."""
    src = (ROOT / "hit_gate.py").read_text(encoding="utf-8")
    assert '"session_status"' in src
    assert '"pipeline"' in src
    assert '"status": "SUCCESS"' not in src and '"status": "COMPLETED"' not in src
    assert '"status": "INVALID_URL"' not in src


def test_payment_pages_requests_are_alert_wired():
    """Каждый запрос к payment_pages должен проверяться на выведенный маршрут (H-01).

    Живой замер: весь вектор /hit живёт на /v1/payment_pages/{cs} и /confirm, поэтому 404 там
    обязан кричать «контур развалился». Раньше алерт стоял только на трёх маршрутах из четырёх.
    """
    for rel, window in (("hit_gate.py", 24), ("frictionless_engine.py", 24)):
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        req_lines = [i for i, ln in enumerate(lines)
                     if "api.stripe.com/v1/payment_pages" in ln]
        assert req_lines, f"{rel}: не найдено обращений к payment_pages — тест потерял смысл"
        for idx in req_lines:
            near = "\n".join(lines[idx:idx + window])
            assert "flag_internal_endpoint" in near, (
                f"{rel}:{idx + 1} — обращение к payment_pages без проверки на выведенный маршрут"
            )
    ctok = (ROOT / "gate_client.py").read_text(encoding="utf-8").splitlines()
    ctok_lines = [i for i, ln in enumerate(ctok)
                  if 'ctok_url = "https://api.stripe.com/v1/confirmation_tokens"' in ln]
    assert ctok_lines, "не найдено обращение к confirmation_tokens"
    for idx in ctok_lines:
        near = "\n".join(ctok[idx:idx + 24])
        assert "flag_internal_endpoint" in near, (
            f"gate_client.py:{idx + 1} — ctoken без проверки на выведенный маршрут"
        )


def test_no_status_literals_outside_taxonomy():
    """Ни один прод-модуль не имеет права отдавать статус вне таксономии (M-06 / G-10).

    Скан был разовым при проверке раздела; теперь это постоянный сторож: статус-литералы
    из корневых модулей и bot/ обязаны лежать в config.VERDICTS или config.SCAN_STATUSES.
    """
    rx_status = re.compile(r"['\"]status['\"]\s*:\s*['\"]([A-Z][A-Z0-9_@]*)")
    rx_return = re.compile(r"return\s*\(?\s*['\"]([A-Z][A-Z0-9_@]{2,})['\"]")
    allowed = set(config.VERDICTS) | set(config.SCAN_STATUSES)
    offenders: list[str] = []
    modules = [p for p in ROOT.glob("*.py") if not p.name.startswith("_")]
    modules += [p for p in (ROOT / "bot").rglob("*.py") if not p.name.startswith("_")]
    for path in modules:
        text = path.read_text(encoding="utf-8", errors="replace")
        for rx in (rx_status, rx_return):
            for m in rx.finditer(text):
                if m.group(1) not in allowed:
                    offenders.append(f"{path.name}: {m.group(1)}")
    assert not offenders, (
        "статусы вне таксономии и SCAN_STATUSES: " + ", ".join(sorted(set(offenders))[:15])
    )


def test_scan_statuses_are_not_verdicts():
    """Статусы сканера — отдельное множество: их нельзя принять за вердикт карты."""
    assert config.SCAN_STATUSES, "SCAN_STATUSES не должен быть пустым"
    assert not (set(config.SCAN_STATUSES) & set(config.VERDICTS)), \
        "статусы сканера не должны пересекаться с вердиктами"
    for st in ("CAPTCHA_CHECKOUT", "GUEST_CHECKOUT_DISABLED"):
        assert st in config.VERDICTS, f"{st} должен быть в таксономии"
        assert st in config.VERDICT_ICONS, f"{st} без иконки"
        assert config.coerce_verdict(st) == "ERROR"
        assert config.is_refundable(st) is True
    assert "CHALLENGE_PASSED" in config.VERDICTS
    assert "CHALLENGE_PASSED" in config.VERDICT_ICONS
    assert config.coerce_verdict("CHALLENGE_PASSED") == "CHALLENGE_PASSED"
