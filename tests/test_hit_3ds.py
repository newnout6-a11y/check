# language: Python 3.12+, file: tests/test_hit_3ds.py, target: Windows 11
import pytest
from hit_gate import CsHitSession

@pytest.mark.asyncio
async def test_classify_success_paid():
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    session.amount = 500
    session.currency = "USD"
    
    verdict, detail = await session._classify_and_resolve_3ds({"status": "complete"})
    assert verdict == "APPROVED@PAID"
    
    verdict2, detail2 = await session._classify_and_resolve_3ds({"payment_status": "paid"})
    assert verdict2 == "APPROVED@PAID"
    
    verdict3, detail3 = await session._classify_and_resolve_3ds({
        "payment_intent": {"status": "succeeded"}
    })
    assert verdict3 == "APPROVED@PAID"

@pytest.mark.asyncio
async def test_classify_card_errors():
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    
    # Insufficient funds
    verdict, detail = await session._classify_and_resolve_3ds({
        "error": {
            "code": "card_declined",
            "decline_code": "insufficient_funds",
            "message": "Your card has insufficient funds."
        }
    })
    assert verdict == "APPROVED@CVV"
    
    # Incorrect CVC
    verdict, detail = await session._classify_and_resolve_3ds({
        "error": {
            "code": "incorrect_cvc",
            "message": "Your card's security code is incorrect."
        }
    })
    assert verdict == "APPROVED@CCN"
    
    # Lost / Stolen
    verdict, detail = await session._classify_and_resolve_3ds({
        "error": {
            "code": "card_declined",
            "decline_code": "stolen_card",
            "message": "Your card was declined."
        }
    })
    assert verdict == "DECLINED@STOLEN"

@pytest.mark.asyncio
async def test_classify_3ds2_challenge_acs():
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    
    # 3DS2 Challenge direct from SDK
    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "stripe_3ds2_challenge",
                    "stripe_js": {
                        "acs_url": "https://acs.bank.com/challenge",
                        "creq": "eyJ..."
                    }
                }
            }
        }
    }
    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "3DS_CHALLENGE"
    assert "OTP/SMS" in detail

@pytest.mark.asyncio
async def test_classify_3ds2_fingerprint_fallback():
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    
    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "stripe_3ds2_fingerprint",
                    "three_d_secure_2_source": "src_mock123"
                }
            }
        }
    }
    # Без открытой сессии (s=None)
    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "3DS_CHALLENGE"
    assert "3DS2 enrolled" in detail

def test_amount_mismatch_predicate_message_variant():
    """Живой кейс 06.09: код checkout_amount_mismatch лежит в message, не в code."""
    from hit_gate import _amount_mismatch
    live_err = {"message": "The computed invoice amount does not match the latest invoice on the subscription. checkout_amount_mismatch"}
    assert _amount_mismatch(400, live_err) is True
    assert _amount_mismatch(400, {"code": "checkout_amount_mismatch"}) is True
    assert _amount_mismatch(400, {"decline_code": "amount_mismatch"}) is True
    # не-mismatch и не-метод
    assert _amount_mismatch(400, {"code": "card_declined", "message": "Your card was declined."}) is False
    assert _amount_mismatch(200, live_err) is False


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._p = payload

    def json(self):
        return self._p


class _DummySession:
    """Последовательность ответов для полного каскада check_card."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("POST", url))
        return self.script.pop(0)

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url))
        return self.script.pop(0)


async def _quiet_profile(card_raw, quiet=True):
    from bin_steering import CardProfile, ThreeDsCategory
    return CardProfile(pan="x", bin6="x", category=ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                       confidence_score=0.5, reason="test")


@pytest.mark.asyncio
async def test_check_card_cascade_survives_message_mismatch(monkeypatch):
    """confirm 400 с amount_mismatch в MESSAGE -> перечитать сумму -> повтор -> complete."""
    import hit_gate as hg
    from bin_steering import BinSteeringEngine

    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_t#fid")
    sess.s = _DummySession([
        _Resp(200, {"status": "open"}),                                    # _alive GET
        _Resp(200, {"id": "pm_test_1"}),                                   # tokenize
        _Resp(400, {"error": {"message": "The computed invoice amount does not "
                                    "match the latest invoice on the subscription. "
                                    "checkout_amount_mismatch"}}),          # confirm 1
        _Resp(200, {"total_summary": {"due": 1425}, "status": "open"}),    # re-read
        _Resp(200, {"status": "complete"}),                                # confirm 2
    ])
    sess.pk, sess.cs, sess.amount, sess.currency = "pk_live_x", "cs_live_t", 1317, "SGD"
    monkeypatch.setattr(BinSteeringEngine, "evaluate_card", _quiet_profile)

    res = await sess.check_card("4111111111111111|12|28|123")
    assert res["status"] == "APPROVED@PAID"
    assert res["amount_cents"] == 1425          # сумма пересчитана каскадом
    assert sess.confirms == 2                   # оба confirmа в бюджете


@pytest.mark.asyncio
async def test_check_card_double_mismatch_is_error(monkeypatch):
    """mismatch и после пересчёта — дрейф прейлиста: ERROR (свойство цели), не DECLINED."""
    import hit_gate as hg
    from bin_steering import BinSteeringEngine

    mismatch = _Resp(400, {"error": {"message": "amount_mismatch: invoice changed"}})
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_t#fid")
    sess.s = _DummySession([
        _Resp(200, {"status": "open"}),                                    # _alive GET
        _Resp(200, {"id": "pm_test_1"}),
        _Resp(400, {"error": {"message": "amount_mismatch: invoice changed"}}),
        _Resp(200, {"total_summary": {"due": 1500}, "status": "open"}),
        _Resp(400, {"error": {"message": "amount_mismatch: invoice changed again"}}),
    ])
    sess.pk, sess.cs, sess.amount, sess.currency = "pk_live_x", "cs_live_t", 1317, "SGD"
    monkeypatch.setattr(BinSteeringEngine, "evaluate_card", _quiet_profile)

    res = await sess.check_card("4111111111111111|12|28|123")
    assert res["status"] == "ERROR"
    assert "дрейфует" in res["detail"]
    # ERROR refundable — кредит вернётся
    import config
    assert config.is_refundable(res["status"]) is True


@pytest.mark.asyncio
async def test_classify_radar_bot_challenge():
    """intent_confirmation_challenge — Stripe Radar hCaptcha, не 3DS (не enrolled)."""
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    
    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "mock_rqdata_blob",
                }
            }
        }
    }
    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "CAPTCHA_CHECKOUT"
    assert "Radar" in detail
    assert "hCaptcha" in detail
    # sitekey виден в детале для диагностики цели
    assert "c7faac4c" in detail
    # и coerce ведёт себя как техстатус цели: ERROR-класс -> refund + фолл-троу
    import config
    assert config.coerce_verdict(verdict) == "ERROR"


@pytest.mark.asyncio
async def test_classify_3ds1_redirect():
    session = CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    
    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "redirect_to_url",
                "redirect_to_url": {
                    "url": "https://hooks.stripe.com/three_d_secure/authenticate?source=src_123"
                }
            }
        }
    }
    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "3DS_CHALLENGE"
    assert "redirect challenge" in detail
