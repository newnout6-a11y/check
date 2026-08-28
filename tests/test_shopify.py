# language: Python 3.12+, file: tests/test_shopify.py, target: Windows 11
# Comprehensive offline unit tests for Shopify gate, bot plugin, and verdict taxonomy.
import pytest
from bot.gates import load_gates
from bot.gates import shopify as bg_shopify
import shopify_gate as sg


def test_card_normalization_valid():
    card = sg._normalize_card("4111111111111111|12|2030|123")
    assert card is not None
    assert card["number"] == "4111111111111111"
    assert card["mm"] == "12"
    assert card["yy"] == "2030"
    assert card["cvc"] == "123"


def test_card_normalization_two_digit_year():
    card = sg._normalize_card("4111111111111111:05:32:999")
    assert card is not None
    assert card["mm"] == "05"
    assert card["yy"] == "2032"
    assert card["cvc"] == "999"


def test_card_normalization_invalid_luhn():
    assert sg._normalize_card("4111111111111112|12|2030|123") is None


def test_card_normalization_invalid_month():
    assert sg._normalize_card("4111111111111111|13|2030|123") is None
    assert sg._normalize_card("4111111111111111|00|2030|123") is None


def test_classify_verdict_paid():
    v1, _ = sg.classify_shopify_verdict({"__typename": "SubmitSuccess", "receipt": {"__typename": "ProcessedReceipt", "orderStatusPageUrl": "https://store.myshopify.com/orders/123"}})
    assert v1 == "APPROVED@PAID"

    v2, _ = sg.classify_shopify_verdict("Thank you for your purchase! Your order is confirmed.", "https://store.myshopify.com/checkouts/123/thank_you")
    assert v2 == "APPROVED@PAID"


def test_classify_verdict_3ds():
    v1, _ = sg.classify_shopify_verdict({"__typename": "SubmittedForCompletion", "receipt": {"__typename": "ActionRequiredReceipt", "token": "tok_3ds"}})
    assert v1 == "3DS_REQUIRED"

    v2, _ = sg.classify_shopify_verdict("3DS authentication required", "https://store.myshopify.com/3d_secure/redirect")
    assert v2 == "3DS_REQUIRED"


def test_classify_verdict_insufficient_funds():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "insufficient_funds"})
    assert v == "APPROVED@CVV"

    v2, _ = sg.classify_shopify_verdict("Card was declined: Insufficient funds in account.")
    assert v2 == "APPROVED@CVV"


def test_classify_verdict_incorrect_cvc():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "incorrect_cvc"})
    assert v == "APPROVED@CCN"

    v2, _ = sg.classify_shopify_verdict("The security code was incorrect. Please check your CVV.")
    assert v2 == "APPROVED@CCN"


def test_classify_verdict_do_not_honor():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "do_not_honor"})
    assert v == "DECLINED@DO_NOT_HONOR"


def test_classify_verdict_fraud():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "fraudulent_transaction"})
    assert v == "DECLINED@FRAUD"


def test_classify_verdict_stolen():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "stolen_card"})
    assert v == "DECLINED@STOLEN"


def test_classify_verdict_expired():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "expired_card"})
    assert v == "EXPIRED"


def test_classify_verdict_invalid_number():
    v, _ = sg.classify_shopify_verdict({"__typename": "SubmitFailed", "reason": "invalid_number"})
    assert v == "INVALID"


def test_classify_verdict_throttled():
    v, _ = sg.classify_shopify_verdict({"__typename": "Throttled", "pollAfter": 5})
    assert v == "RATE_LIMITED"


def test_classify_verdict_checkpoint():
    v, _ = sg.classify_shopify_verdict({"__typename": "CheckpointDenied", "redirectUrl": "/challenge"})
    assert v == "ERROR"


def test_parse_tiers_shopify():
    assert bg_shopify.parse_tier("1") == (0, 100)
    assert bg_shopify.parse_tier("5") == (101, 500)
    assert bg_shopify.parse_tier("20") == (501, 2000)
    assert bg_shopify.parse_tier("low") == (0, 200)
    assert bg_shopify.parse_tier("MID") == (201, 600)
    assert bg_shopify.parse_tier("high") == (601, 2000)
    assert bg_shopify.parse_tier("invalid") is None
    assert bg_shopify.parse_tier("4111111111111111") is None


def test_shopify_targets_loaded():
    targets = bg_shopify._targets()
    assert len(targets) >= 5
    assert all(t.startswith("http") for t in targets)


def test_shopify_targets_tier_filtering():
    t_low = bg_shopify._targets(tier=bg_shopify.parse_tier("1"))
    t_mid = bg_shopify._targets(tier=bg_shopify.parse_tier("5"))
    t_high = bg_shopify._targets(tier=bg_shopify.parse_tier("20"))

    assert len(t_low) > 0
    assert len(t_mid) > 0
    assert len(t_high) > 0


def test_bot_registry_contains_shopify():
    registry = load_gates()
    assert "shopify" in registry
    assert registry["shopify"]["cost"] == 2
    assert callable(registry["shopify"]["fn"])


@pytest.mark.asyncio
async def test_bot_gate_invalid_card():
    verdict, detail = await bg_shopify.gate("4111111111111112", "12", "30", "123")
    assert verdict == "INVALID"
    assert "Luhn" in detail


@pytest.mark.asyncio
async def test_bot_gate_invalid_tier():
    verdict, detail = await bg_shopify.gate("4111111111111111", "12", "30", "123", tier="999")
    assert verdict == "ERROR"
    assert "неизвестный" in detail.lower() or "unknown" in detail.lower()
