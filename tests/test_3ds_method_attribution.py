# language: Python 3.12+, file: tests/test_3ds_method_attribution.py, target: Windows 11
"""Атрибуция после 3DS-Method: frictionless / челлендж / «метод ушёл без ответа».

Живой случай 2026-09-13 (Kimi/Stripe, Amex SafeKey): Method получал 200, но единственный опрос
сразу после него ещё видел next_action=stripe_3ds2_fingerprint, движок возвращал IN_PROGRESS,
и hit_gate выдавал «3DS2 enrolled» — то есть проход и челлендж не различались.
"""
import pytest

import config
import frictionless_engine as fe


class _Resp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class _Session:
    """post — Method, get — опросы сессии (по одному ответу на вызов)."""

    def __init__(self, polls, method_status=200):
        self._polls = list(polls)
        self._method_status = method_status
        self.cookies = None
        self.polls_done = 0

    async def post(self, url, data=None, headers=None, timeout=None):
        return _Resp(self._method_status, "<html><body>acs</body></html>")

    async def get(self, url, params=None, headers=None, timeout=None):
        self.polls_done += 1
        if self._polls:
            return _Resp(200, "", self._polls.pop(0))
        return _Resp(200, "", {})


def _pi(status, sdk_type="", acs_url=""):
    na = {"use_stripe_sdk": {"type": sdk_type}} if sdk_type else {}
    if acs_url:
        na = {"use_stripe_sdk": {"type": sdk_type, "acs_url": acs_url}}
    out = {"payment_intent": {"status": status}}
    if na:
        out["payment_intent"]["next_action"] = na
    return out


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(config, "THREE_DS_METHOD_POLL_DELAY_S", 0.0, raising=False)


@pytest.mark.asyncio
async def test_polls_until_acs_confirms_and_reports_evidence():
    """ACS подтверждает на втором опросе — вердикт frictionless с подтверждением Stripe."""
    s = _Session([_pi("requires_action", "stripe_3ds2_fingerprint"),
                  {"payment_intent": {"status": "succeeded"}}])
    res = await fe.attempt_frictionless_resolution(
        s, "pk_live_x", "cs_live_x",
        {"three_ds_method_url": "https://secure2.arcot.com/tds-method", "server_transaction_id": "tid-1"},
    )
    assert res["outcome"] == "FRICTIONLESS_PASSED"
    assert res["evidence"] == "pi_succeeded"
    assert s.polls_done >= 2


@pytest.mark.asyncio
async def test_method_without_acs_answer_is_not_reported_as_frictionless():
    """Все опросы показывают fingerprint — это METHOD_ONLY, а не проход."""
    s = _Session([_pi("requires_action", "stripe_3ds2_fingerprint")] * 6)
    res = await fe.attempt_frictionless_resolution(
        s, "pk_live_x", "cs_live_x",
        {"three_ds_method_url": "https://secure2.arcot.com/tds-method", "server_transaction_id": "tid-2"},
    )
    assert res["outcome"] == "METHOD_ONLY"
    assert "не подтвердил" in res["detail"]
    assert s.polls_done == int(getattr(config, "THREE_DS_METHOD_POLL_ROUNDS", 4))


@pytest.mark.asyncio
async def test_challenge_next_action_wins_over_retries():
    """Как только Stripe выкатил challenge/acs_url — фиксируем челлендж, дальше не опрашиваем."""
    s = _Session([_pi("requires_action", "stripe_3ds2_fingerprint"),
                  _pi("requires_action", "stripe_3ds2_challenge", acs_url="https://acs.example/otp")])
    res = await fe.attempt_frictionless_resolution(
        s, "pk_live_x", "cs_live_x",
        {"three_ds_method_url": "https://secure2.arcot.com/tds-method", "server_transaction_id": "tid-3"},
    )
    assert res["outcome"] == "CHALLENGE_REQUIRED"
    assert s.polls_done == 2


@pytest.mark.asyncio
async def test_complete_session_without_payment_still_reports_unpaid_evidence():
    """Сессия complete и unpaid — это провал верификации, а не оплата."""
    s = _Session([{"status": "complete", "payment_status": "unpaid", "payment_intent": {"status": "requires_payment_method"}}])
    res = await fe.attempt_frictionless_resolution(
        s, "pk_live_x", "cs_live_x",
        {"three_ds_method_url": "https://secure2.arcot.com/tds-method", "server_transaction_id": "tid-4"},
    )
    assert res["outcome"] == "FRICTIONLESS_PASSED"
    assert res["evidence"] == "session_complete_unpaid"


@pytest.mark.asyncio
async def test_no_method_call_leaves_outcome_in_progress():
    """Без Method и без подтверждения — прежний IN_PROGRESS, а не выдуманный вердикт."""
    s = _Session([_pi("requires_action", "stripe_3ds2_fingerprint")] * 6)
    res = await fe.attempt_frictionless_resolution(s, "pk_live_x", "cs_live_x", {})
    assert res["outcome"] == "IN_PROGRESS"
