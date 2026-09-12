# language: Python 3.12+, file: tests/test_auth_failure_verdict.py, target: Windows 11
"""Провал верификации способа оплаты — отдельный класс, а не отказ карты и не оплата.

Живой случай dj 2026-09-12: страница Stripe показала «Не удалось верифицировать способ оплаты.
Выберите другой способ оплаты и повторите попытку», а прогон /hit в тот же момент отрапортовал
APPROVED@PAID, потому что завершение сессии (status=complete) принималось за оплату.
"""
from __future__ import annotations

import config
import frictionless_engine as fe
import gate_client as gc


def test_pi_authentication_failure_is_challenge_failed():
    verdict, detail = gc.classify_pi_verdict({
        "error": {"code": "payment_intent_authentication_failure",
                  "message": "We were unable to verify your payment method."}
    })
    assert verdict == "CHALLENGE_FAILED", (verdict, detail)
    assert config.is_refundable(verdict) is True


def test_setupintent_classifier_knows_russian_page_text():
    """Витрина отдаёт текст, а не код: русская формулировка тоже обязана попадать в класс."""
    verdict = gc.classify_verdict(
        "Не удалось верифицировать способ оплаты. Выберите другой способ оплаты и повторите попытку."
    )
    assert verdict == "CHALLENGE_FAILED", verdict
    assert gc.classify_verdict("We could not verify your payment method") == "CHALLENGE_FAILED"


def test_declines_are_still_declines():
    """Настоящие отказы не должны попадать в класс верификации."""
    assert gc.classify_verdict("Your card was declined. card_declined") == "DECLINED"
    assert gc.classify_verdict("Insufficient funds") == "APPROVED@CVV"
    assert gc.classify_pi_verdict({"error": {"code": "incorrect_number",
                                             "message": "Your card number is incorrect."}})[0] == "INVALID"


def test_completed_session_without_payment_is_not_paid():
    """status=complete при payment_status=unpaid — это провал верификации, а не оплата."""
    assert fe._evidence_from_poll({"status": "complete", "payment_status": "unpaid"}) == "session_complete_unpaid"
    assert fe._evidence_from_poll({"status": "complete", "payment_status": "paid"}) == "session_paid"
    assert fe._evidence_from_poll({"payment_intent": {"status": "succeeded"}}) == "pi_succeeded"
    assert fe._evidence_from_poll({"payment_intent": {"status": "processing"}}) == "pi_processing"
    assert fe._evidence_from_poll({"status": "open", "payment_status": "unpaid"}) == ""
