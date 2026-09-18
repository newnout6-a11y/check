# language: Python 3.12+, file: tests/test_confirm_amount_presentment.py, target: Windows 11
"""Сумма и параметры confirm: живые факты 2026-09-13 с hosted checkout.

1) expected_amount должен быть в валюте ВИТРИНЫ: PI 1900 USD против инвойса 2504 SGD — на валюте PI
   confirm отвечает 400 checkout_amount_mismatch, и попытка сгорает не из-за карты.
2) radar_options[hcaptcha_token] этот маршрут не принимает вообще: первый же confirm отвечает
   400 parameter_unknown, а сама страница Stripe шлёт токен как passive_captcha_token.
"""
import pytest

import config
import hit_gate as hg


def test_presentment_amount_from_total_summary():
    data = {"payment_intent": {"amount": 1900}, "total_summary": {"due": 2504}}
    assert hg.presentment_amount(data) == 2504


def test_presentment_amount_from_invoice_object():
    assert hg.presentment_amount({"invoice": {"amount_due": 37200}}) == 37200


def test_presentment_amount_when_absent():
    assert hg.presentment_amount({}) == 0
    assert hg.presentment_amount({"invoice": "in_123"}) == 0
    assert hg.presentment_amount(None) == 0


def _session():
    s = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    s.pk = "pk_live_test"
    s.cs = "cs_live_test"
    s.amount = 1900
    s.expected_amount = 2504
    s.checksum = "checksum-1"
    return s


def test_confirm_body_uses_presentment_amount():
    body = _session().confirm_body({"id": "pm_test"}, {})
    assert body["expected_amount"] == "2504"
    assert body["expected_payment_method_type"] == "card"
    assert body["init_checksum"] == "checksum-1"


def test_confirm_body_falls_back_to_pi_amount_when_presentment_unknown():
    s = _session()
    s.expected_amount = 0
    assert s.confirm_body({"id": "pm_test"}, {})["expected_amount"] == "1900"


def test_radar_options_not_sent_by_default(monkeypatch):
    """У маршрута нет такого параметра — дефолт False, иначе каждый confirm начинается с 400."""
    monkeypatch.setattr(config, "CONFIRM_SEND_RADAR_OPTIONS", False, raising=False)
    s = _session()
    s.hcaptcha_token = "P1_fake_token"
    body = s.confirm_body({"id": "pm_test"}, {})
    assert "radar_options[hcaptcha_token]" not in body


def test_radar_options_flag_allows_rollback(monkeypatch):
    monkeypatch.setattr(config, "CONFIRM_SEND_RADAR_OPTIONS", True, raising=False)
    s = _session()
    s.hcaptcha_token = "P1_fake_token"
    body = s.confirm_body({"id": "pm_test"}, {})
    assert body["radar_options[hcaptcha_token]"] == "P1_fake_token"


def test_money_prints_major_units_and_currency():
    """Живой дефект 2026-09-18: «PI 1900USD» — $19.00 читалось как тысяча девятьсот."""
    assert hg.money(1900, "usd") == "19.00 USD"
    assert hg.money(2504, "SGD") == "25.04 SGD"
    assert hg.money(0, "usd") == "0.00 USD"
    assert hg.money(5, "usd") == "0.05 USD"


def test_money_respects_zero_decimal_currencies():
    """У JPY/KRW сотых нет: деление на 100 там врёт."""
    assert hg.money(1329, "jpy") == "1329 JPY"
    assert hg.money(50000, "KRW") == "50000 KRW"


def test_money_survives_garbage():
    assert hg.money(None, "usd") == "0.00 USD"
    assert hg.money("not-a-number", "usd") == "? USD"
    assert hg.money("1900", "usd") == "19.00 USD"


def test_presentment_currency_prefers_session_over_pi():
    """Валюта подтверждения — валюта витрины, а не PI: PI 1900 USD против инвойса 2504 SGD."""
    assert hg.presentment_currency({"currency": "sgd", "invoice": {"currency": "usd"}}, "usd") == "SGD"
    assert hg.presentment_currency({"invoice": {"currency": "sgd"}}, "usd") == "SGD"
    assert hg.presentment_currency({}, "usd") == "USD"
    assert hg.presentment_currency(None, "usd") == "USD"
    assert hg.presentment_currency({"invoice": "in_123"}, "usd") == "USD"


def test_session_origin_matches_hosted_checkout_page():
    """Живой перехват 2026-09-18: страница шлёт confirm с Origin https://checkout.stripe.com,
    а не js.stripe.com — это единственный заголовок, которым наш confirm от неё отличался."""
    assert hg.session_origin("https://checkout.stripe.com/c/pay/cs_live_x#fid") == "https://checkout.stripe.com"
    assert hg.session_origin("") == "https://checkout.stripe.com"
    assert hg.session_origin("https://pay.example.org/c/pay/cs_live_y") == "https://pay.example.org"


def test_amount_mismatch_still_detected_by_message_tail():
    """Живой кейс: code=None, текст ошибки в message."""
    assert hg._amount_mismatch(400, {"code": None, "message": "subscription.invoice_proration.checkout_amount_mismatch"})
    assert not hg._amount_mismatch(200, {"message": "ok"})
