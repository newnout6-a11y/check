# language: Python, file: tests/test_audit_crit_fixes.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import config
import gate_client as gc
import hit_gate
from bot.gates import braintreenvbv, storegate


def test_crit_03_cf_challenge_marks_no_turnstile_wrapper():
    """CRIT-03: Legitimate Turnstile wrapper div must NOT trigger is_cloudflare_challenge."""
    turnstile_checkout_html = (
        '<html><body>'
        '<form class="checkout">'
        '<div class="cf-turnstile-wrapper" data-sitekey="0x4AAAAAA">'
        '<input type="hidden" name="cf-turnstile-response" value="">'
        '</div></form></body></html>'
    )
    assert not gc.is_cloudflare_challenge(turnstile_checkout_html)

    # Real Cloudflare block screens must still trigger
    assert gc.is_cloudflare_challenge("<html><title>Just a moment...</title></html>")
    assert gc.is_cloudflare_challenge("<html>Attention Required! | Cloudflare</html>")
    assert gc.is_cloudflare_challenge('<script src="/cdn-cgi/challenge-platform/scripts/"></script>')


def test_crit_06_is_refundable_coerces_merchant_failures():
    """CRIT-06: Merchant/store failures must be refundable even without prior coercion."""
    # Standard refundable
    assert config.is_refundable("ERROR")
    assert config.is_refundable("SESSION_EXPIRED")
    assert config.is_refundable("SESSION_CANCELED")

    # Uncoerced merchant failures
    assert config.is_refundable("CAPTCHA_CHECKOUT")
    assert config.is_refundable("GUEST_CHECKOUT_DISABLED")
    assert config.is_refundable("GUEST_CHECKOUT_OFF")
    assert config.is_refundable("NO_PM_SLUG")
    assert config.is_refundable("NO_PRODUCT_UNDER_CAP")
    assert config.is_refundable("OUT_OF_STOCK")
    assert config.is_refundable("CART_EMPTY")
    assert config.is_refundable("CHECKPOINT_DENIED")

    # Legitimate card verdicts must NEVER be refunded
    assert not config.is_refundable("APPROVED")
    assert not config.is_refundable("DECLINED")
    assert not config.is_refundable("DECLINED@DO_NOT_HONOR")
    assert not config.is_refundable("DECLINED@FRAUD")
    assert not config.is_refundable("3DS_REQUIRED")


@pytest.mark.asyncio
async def test_crit_04_turnstile_sidecar_in_running_loop():
    """CRIT-04: solve_turnstile must not crash with RuntimeError when called inside an event loop."""
    import turnstile_sidecar

    # In an active loop, solve_turnstile delegates to ThreadPoolExecutor or returns None cleanly
    with patch("turnstile_sidecar.solve_turnstile_async", new_callable=AsyncMock) as mock_solve:
        mock_solve.return_value = "0xTOKEN123"
        # Calling synchronous wrapper inside running loop
        res = turnstile_sidecar.solve_turnstile("https://example.com/checkout", timeout_sec=2.0)
        assert res == "0xTOKEN123"

    # Also test async exported helper
    with patch("turnstile_sidecar.solve_turnstile_async", new_callable=AsyncMock) as mock_solve_async:
        mock_solve_async.return_value = "0xTOKEN_ASYNC"
        res_async = await gc.solve_turnstile_url_async("https://example.com/checkout", timeout_sec=2.0)
        assert res_async == "0xTOKEN_ASYNC"


@pytest.mark.asyncio
async def test_crit_05_hit_gate_session_expired():
    """CRIT-05: CsHitSession must return SESSION_EXPIRED on dead Stripe session."""
    session = hit_gate.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test")
    session.s = MagicMock()  # pretend session opened

    with patch.object(session, "_alive", new_callable=AsyncMock) as mock_alive:
        mock_alive.return_value = False
        res = await session.check_card("4111111111111111|12|28|123")
        assert res["status"] == "SESSION_EXPIRED"
        assert "expired or completed" in res["detail"].lower()


@pytest.mark.asyncio
async def test_crit_02_braintreenvbv_returns_3_tuple_with_proxy():
    """CRIT-02: braintreenvbv.gate must return a 3-tuple (status, detail, extra) with proxy."""
    # Invalid card format
    res_inv = await braintreenvbv.gate("4111", "12", "28", "123")
    assert len(res_inv) == 3
    assert res_inv[0] == "INVALID"
    assert isinstance(res_inv[2], dict)

    # Empty targets
    with patch.object(braintreenvbv, "_targets", return_value=[]):
        res_err = await braintreenvbv.gate("4111111111111111", "12", "28", "123")
        assert len(res_err) == 3
        assert res_err[0] == "ERROR"
        assert isinstance(res_err[2], dict)

    # With target and mocked response
    with patch.object(braintreenvbv, "_targets", return_value=["https://braintree-store.com"]), \
         patch("gate_client.load_proxies", return_value=["socks5://127.0.0.1:9050"]), \
         patch("gate_client.braintree_vbv_check", new_callable=AsyncMock) as mock_check, \
         patch("curl_cffi.requests.AsyncSession.get", new_callable=AsyncMock) as mock_get:
        mock_check.return_value = {"status": "APPROVED", "detail": "cvv passed"}
        mock_get.return_value = MagicMock(text="<html>braintree client token</html>")

        res_ok = await braintreenvbv.gate("4111111111111111", "12", "28", "123")
        assert len(res_ok) == 3
        assert res_ok[0] == "APPROVED"
        assert res_ok[2].get("proxy") == "socks5://127.0.0.1:9050"
        assert res_ok[2].get("target") == "https://braintree-store.com"


def test_crit_07_storegate_tier_cap_preservation():
    """CRIT-07: Tier 1 request must maintain $1 (100c) cap and not override to $20 (2000c)."""
    t_window_1 = storegate.parse_tier("1")
    assert t_window_1 == (0, 100)

    # Simulated line 143 logic
    max_price_1 = t_window_1[1] if t_window_1 else storegate.MAX_PRICE_CENTS
    assert max_price_1 == 100  # $1.00 exactly, NOT $20.00!

    t_window_5 = storegate.parse_tier("5")
    max_price_5 = t_window_5[1] if t_window_5 else storegate.MAX_PRICE_CENTS
    assert max_price_5 == 500  # $5.00

    max_price_none = None if None else storegate.MAX_PRICE_CENTS
    assert max_price_none == 2000  # default $20.00


def test_crit_08_storegate_dead_domains_includes_unverified():
    """CRIT-08: _dead_domains() must include domains where verified is False or blocked."""
    sample_gates = [
        {"domain": "goodstore.com", "verified": True},
        {"domain": "failedstore.com", "verified": False},
        {"domain": "blockedstore.com", "blocked": True},
        {"domain": "deadstore.com", "dead_surface": True},
        {"domain": "phantomstore.com", "phantom": True},
    ]
    with patch("builtins.open", MagicMock()), patch("json.load", return_value=sample_gates):
        dead = storegate._dead_domains()
        assert "failedstore.com" in dead
        assert "blockedstore.com" in dead
        assert "deadstore.com" in dead
        assert "phantomstore.com" in dead
        assert "goodstore.com" not in dead


@pytest.mark.asyncio
async def test_crit_01_cmd_bin_no_nameerror():
    """CRIT-01: cmd_bin must not raise NameError on status_msg."""
    from bot import main as bot_main

    mock_msg = MagicMock()
    mock_msg.text = "/bin 453211"
    mock_msg.from_user.id = 123456
    mock_msg.from_user.username = "testuser"
    mock_status = MagicMock()
    mock_status.edit_text = AsyncMock()
    mock_msg.reply = AsyncMock(return_value=mock_status)

    with patch("setup_gate.bin_lookup", new_callable=AsyncMock), \
         patch("bin_cache.cached_lookup", new_callable=AsyncMock) as mock_cached:
        mock_cached.return_value = {
            "scheme": "VISA",
            "type": "CREDIT",
            "level": "CLASSIC",
            "bank": {"name": "CHASE"},
            "country": {"name": "UNITED STATES", "alpha2": "US"},
            "is_vbv": True,
        }
        await bot_main.cmd_bin(None, mock_msg)
        mock_msg.reply.assert_called()
        mock_status.edit_text.assert_called_once()
        sent_text = mock_status.edit_text.call_args[0][0]
        assert "CHASE" in sent_text
        assert "VISA" in sent_text
