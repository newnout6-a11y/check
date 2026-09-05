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
