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


def test_internal_endpoint_gone_is_flagged_only_for_internal_paths():
    """404 на непубличном маршруте — сигнал развала контура; 404 на обычном — нет."""
    internal = "https://api.stripe.com/v1/payment_intents/pi_1/verify_challenge"
    assert gc.flag_internal_endpoint(_Resp(404, {}), internal) is True
    assert gc.flag_internal_endpoint(_Resp(404, {}), "https://api.stripe.com/v1/payment_methods") is False
    assert gc.flag_internal_endpoint(_Resp(401, {}), internal) is False


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
