# language: Python 3.12+, file: tests/test_hit_verdict_fidelity.py, target: Windows 11
"""Вердикт /hit не имеет права подменять класс: «карта жива» — это не «оплачено».

Живой замер 2026-09-12: прогон по живой подписочной сессии отрапортовал APPROVED@PAID,
хотя сессия оставалась payment_status=unpaid, а PI — requires_payment_method. Причины две:
execute_hit превращал ЛЮБОЙ APPROVED* (в том числе APPROVED@CVV/APPROVED@CCN — «карта жива»,
CVV/PAN валидны) в APPROVED@PAID, а frictionless-аутентификация сразу объявляла оплату.
"""
from __future__ import annotations

import asyncio
import pathlib

import config
import hit_gate as hg

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _FakeSession:
    """Сессия-двойник: open() успешен, карта отдаёт заранее заданный вердикт."""

    verdict = "APPROVED@CVV"

    def __init__(self, target_url, **kwargs):
        self.amount = 1900
        self.currency = "SGD"
        self.pi_id = "pi_test"

    async def open(self):
        return True, "ok"

    async def check_card(self, card_raw):
        return {"card": card_raw, "status": type(self).verdict, "detail": "stub"}

    async def close(self):
        return None


def _run_with(verdict: str) -> dict:
    _FakeSession.verdict = verdict
    original = hg.CsHitSession
    hg.CsHitSession = _FakeSession
    try:
        return asyncio.run(hg.execute_hit("https://checkout.stripe.com/c/pay/cs_live_x#fid",
                                         ["4111111111111111|12|30|123"]))
    finally:
        hg.CsHitSession = original


def test_card_liveness_verdict_is_not_reported_as_paid():
    for verdict in ("APPROVED@CVV", "APPROVED@CCN", "APPROVED@HOLD"):
        out = _run_with(verdict)
        assert out["status"] == verdict, (verdict, out["status"])
        assert out["paid"] is False, f"{verdict} не является оплатой"
        assert verdict in config.VERDICTS


def test_real_paid_verdict_keeps_paid_flag():
    out = _run_with("APPROVED@PAID")
    assert out["status"] == "APPROVED@PAID"
    assert out["paid"] is True


def test_declines_stay_declines():
    out = _run_with("DECLINED@FRAUD")
    assert out["status"] == "DECLINED@FRAUD"
    assert out["paid"] is False


def test_frictionless_authentication_is_not_payment():
    """3DS_FRICTIONLESS — аутентификация; оплатой её объявлять нельзя."""
    assert "3DS_FRICTIONLESS" in config.VERDICTS
    src = (ROOT / "hit_gate.py").read_text(encoding="utf-8")
    assert 'return "APPROVED@PAID", f"3DS2 frictionless passed' not in src
    assert 'return "3DS_FRICTIONLESS"' in src
