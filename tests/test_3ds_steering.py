# language: Python 3.12+, file: tests/test_3ds_steering.py, target: Windows 11
import asyncio
import base64
import json
import pytest

import bin_steering
from bin_steering import ThreeDsCategory, BinSteeringEngine
import frictionless_engine


@pytest.mark.asyncio
async def test_bin_steering_classification():
    engine = BinSteeringEngine()

    # 1. Known US Commercial / Non-VBV BIN
    p1 = await engine.evaluate_card("4485287641630198|07|2027|606")
    assert p1.category == ThreeDsCategory.DIRECT_CHECKOUT
    assert p1.confidence_score >= 0.80

    # 2. Known US Chime / Bancorp Non-VBV prefix
    p2 = await engine.evaluate_card("4403931234567890|05|2028|123")
    assert p2.category == ThreeDsCategory.DIRECT_CHECKOUT
    assert p2.confidence_score >= 0.80

    # 3. Invalid Luhn
    p3 = await engine.evaluate_card("4485287641630191|07|2027|606")
    assert p3.category == ThreeDsCategory.INVALID

    # 4. Mock EEA check
    cat_eea, score_eea, _ = engine._score_3ds_risk(
        bin6="400000", scheme="VISA", card_type="credit", level="classic",
        country_a2="FR", is_vbv=None
    )
    assert cat_eea == ThreeDsCategory.CHALLENGE_MANDATORY
    assert score_eea <= 0.20

    # 5. Amex SafeKey subprime US issuer (Credit One 379363)
    cat_amex, score_amex, _ = engine._score_3ds_risk(
        bin6="379363", scheme="AMERICAN EXPRESS", card_type="credit", level="",
        country_a2="US", is_vbv=None
    )
    assert cat_amex == ThreeDsCategory.DIRECT_CHECKOUT
    assert score_amex == 0.88

    # 6. Session termination classification in gate_client
    import gate_client as gc
    v_exp, _ = gc.classify_pi_verdict({"error": {"code": "checkout_not_active_session", "message": "This Checkout Session is no longer active."}})
    assert v_exp == "SESSION_EXPIRED"

    v_canc, _ = gc.classify_pi_verdict({"error": {"code": "resource_missing", "message": "This PaymentIntent's payment_method could not be updated because it has a status of canceled."}})
    assert v_canc == "SESSION_CANCELED"


@pytest.mark.asyncio
async def test_bin_steering_split_queue():
    engine = BinSteeringEngine()
    test_cards = [
        "5175461780694255|09|2029|260",  # US Debit -> Frictionless
        "4485287641630198|07|2027|606",  # US Commercial -> Direct
        "4539274130459806|12|2029|535",  # QA -> Challenge
        "4485287641630191|07|2027|606",  # Bad Luhn -> Invalid
    ]
    queue = await engine.split_queue(test_cards)
    
    assert len(queue[ThreeDsCategory.DIRECT_CHECKOUT]) == 1
    assert len(queue[ThreeDsCategory.FRICTIONLESS_CANDIDATE]) == 1
    assert len(queue[ThreeDsCategory.CHALLENGE_MANDATORY]) == 1
    assert len(queue[ThreeDsCategory.INVALID]) == 1
    assert queue[ThreeDsCategory.DIRECT_CHECKOUT][0].bin6 == "448528"


def test_frictionless_build_method_payload():
    trans_id = "test-uuid-1234-5678"
    notif_url = "https://hooks.stripe.com/3ds2/complete"
    
    b64 = frictionless_engine.build_three_ds_method_payload(trans_id, notif_url)
    assert isinstance(b64, str)
    assert "=" not in b64  # Base64URL unpadded
    
    # Round-trip decode
    padded = b64 + "=" * ((4 - len(b64) % 4) % 4)
    raw = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    assert raw["threeDSServerTransID"] == trans_id
    assert raw["threeDSMethodNotificationURL"] == notif_url


def test_frictionless_build_browser_telemetry():
    t_us = frictionless_engine.build_browser_telemetry(country_code="US")
    assert t_us["threeDSCompInd"] == "Y"
    assert t_us["browserColorDepth"] == "24"
    assert int(t_us["browserTZ"]) in (240, 300, 360, 420, 480)
    assert "en-US" in t_us["browserLanguage"]

    t_de = frictionless_engine.build_browser_telemetry(country_code="DE")
    assert int(t_de["browserTZ"]) in (-60, -120)
    assert "de-DE" in t_de["browserLanguage"]
