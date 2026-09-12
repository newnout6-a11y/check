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


def test_amount_mismatch_still_detected_by_message_tail():
    """Живой кейс: code=None, текст ошибки в message."""
    assert hg._amount_mismatch(400, {"code": None, "message": "subscription.invoice_proration.checkout_amount_mismatch"})
    assert not hg._amount_mismatch(200, {"message": "ok"})
