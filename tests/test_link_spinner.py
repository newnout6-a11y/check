# language: Python 3.12+, file: tests/test_link_spinner.py, target: Windows 11
"""Этап 2.5: крутилка ссылки и два найденных живьём дефекта контура.

Проверяется контракт:
  * класс ссылки (сессия с cs_ против платёжной ссылки, которая рождает новую сессию);
  * признак авто-восстановления (новый PaymentIntent, а не первый круг);
  * снятие параметра, названного Stripe, — включая индексированные ключи;
  * технический parameter_unknown даёт ERROR, а не вердикт карты.
"""
from __future__ import annotations

import pathlib

import config
import gate_client as gc
import link_spinner as ls

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_link_kind_detects_session_and_payment_links():
    session_link = ("https://checkout.stripe.com/g/pay/cs_live_a1VqAaOOllgf9ebt"
                    "xfefWUcxVkGRV56lep69wTFbAMg4AeIKvDYceEVg7O#fidnandhYHdW")
    assert ls.link_kind(session_link) == "session"
    assert ls.link_kind("https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsn") == "session"
    assert ls.link_kind("https://buy.stripe.com/abc123XYZ") == "payment"


def test_detect_renewal_ignores_first_round():
    assert ls.detect_renewal("", "pi_1") is False
    assert ls.detect_renewal("pi_1", "pi_1") is False
    assert ls.detect_renewal("pi_1", "pi_2") is True
    assert ls.detect_renewal("pi_1", "") is False


def test_drop_unknown_param_removes_indexed_keys():
    """Живой замер: Stripe назвал radar_options, а в теле был radar_options[hcaptcha_token]."""
    body = {"key": "pk", "radar_options[hcaptcha_token]": "P1_x", "payment_method": "pm_1"}
    assert gc.drop_unknown_param(body, "radar_options") == 1
    assert "radar_options[hcaptcha_token]" not in body
    assert body["payment_method"] == "pm_1"
    assert gc.drop_unknown_param(body, "payment_method") == 1
    assert gc.drop_unknown_param(body, "нет_такого") == 0


def test_parameter_unknown_is_technical_error_not_card_verdict():
    """400 parameter_unknown — сбой нашего тела, а не отказ эмитента (живой замер 2026-09-12)."""
    verdict, detail = gc.classify_pi_verdict(
        {"error": {"code": "parameter_unknown", "message": "Received unknown parameter: radar_options"}}
    )
    assert verdict == "ERROR", (verdict, detail)
    assert config.is_refundable(verdict) is True
    # настоящий отказ поверхности обязан остаться отказом
    assert gc.classify_pi_verdict({"error": {"code": "incorrect_number",
                                             "message": "Your card number is incorrect."}})[0] == "INVALID"
    assert gc.classify_pi_verdict({"status": "processing"})[0] == "PI_PENDING"


def test_probe_session_rejects_link_without_session_id():
    import asyncio
    out = asyncio.run(ls.probe_session("https://checkout.stripe.com/g/pay/no-session#fidnandhYHdW"))
    assert out["ok"] is False
    assert out["reason"]
