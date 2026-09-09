# language: Python 3.12+, file: tests/test_surface_shield_and_hit.py, target: Windows 11
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import surface_shield as ss
import hit_gate as hg
import stripe_fid

def test_surface_shield_cloudflare_detection():
    headers = {"server": "cloudflare", "cf-ray": "8e1234567890abcd-IAD"}
    cookies = "cf_clearance=abc123xyz; __cf_bm=bm123;"
    html = '<html><head><title>My Store</title></head><body>Normal Content</body></html>'
    res = ss.classify_protection(200, headers, cookies, html)
    assert res["waf"] == "cloudflare"
    assert res["is_active_block"] is False
    assert res["bypass_strategy"] == "curl_impersonate_direct"

def test_surface_shield_turnstile_embedded_not_blocked():
    headers = {"server": "cloudflare"}
    cookies = ""
    html = '''
    <html>
      <head><title>Checkout</title></head>
      <body>
        <div class="cf-turnstile-wrapper" data-sitekey="0x4AAAAAAtest123"></div>
      </body>
    </html>
    '''
    res = ss.classify_protection(200, headers, cookies, html)
    assert "cloudflare_turnstile" in res["shields"]
    assert res["sitekeys"]["turnstile"] == "0x4AAAAAAtest123"
    assert res["is_active_block"] is False
    assert res["bypass_strategy"] == "direct_api_or_turnstile_sidecar"

def test_surface_shield_active_cloudflare_challenge():
    headers = {"server": "cloudflare"}
    cookies = ""
    html = '<html><head><title>Just a moment...</title></head><body><script src="/cdn-cgi/challenge-platform/scripts/"></script></body></html>'
    res = ss.classify_protection(403, headers, cookies, html)
    assert res["waf"] == "cloudflare"
    assert res["is_active_block"] is True
    assert res["bypass_strategy"] == "turnstile_sidecar_cdp"

def test_surface_shield_pow_solvers_detected():
    html_altcha = '<div><altcha-widget challengeurl="/api/challenge"></altcha-widget></div>'
    res_altcha = ss.classify_protection(200, {}, "", html_altcha)
    assert "altcha" in res_altcha["shields"]
    assert res_altcha["bypass_strategy"] == "captcha_pow_cpu"

    html_frc = '<div class="frc-captcha" data-sitekey="FC123"></div>'
    res_frc = ss.classify_protection(200, {}, "", html_frc)
    assert "friendly_captcha" in res_frc["shields"]
    assert res_frc["bypass_strategy"] == "captcha_pow_cpu"

def test_surface_shield_datadome_and_akamai():
    # DataDome
    res_dd = ss.classify_protection(403, {"x-datadome": "protected"}, "datadome=123", "<html>geo.captcha-delivery.com</html>")
    assert res_dd["waf"] == "datadome"
    assert res_dd["is_active_block"] is True
    assert res_dd["bypass_strategy"] == "residential_proxy_rotation"

    # Akamai
    res_ak = ss.classify_protection(200, {"server": "AkamaiGHost"}, "_abck=telemetry123", "<html><script src='sensor.js'></script></html>")
    assert res_ak["waf"] == "akamai"
    assert "akamai" in res_ak["shields"]

@pytest.mark.asyncio
async def test_hit_qualify_session_invalid_url():
    res = await hg.qualify_session("https://example.com/not-a-stripe-link")
    assert res["viable"] is False
    assert res["status"] == "INVALID_URL"

@pytest.mark.asyncio
async def test_hit_qualify_session_open_viable():
    mock_payload = {
        "status": "open",
        "livemode": True,
        "is_sandbox_merchant": False,
        "payment_intent": {
            "status": "requires_payment_method",
            "amount": 1500,
            "currency": "usd",
            "payment_method_options": {
                "card": {"request_three_d_secure": "automatic"}
            }
        },
        "mode": "payment",
        "customer": {"address": {"country": "US"}}
    }
    encoded = stripe_fid.encode_fragment({"apiKey": "pk_live_123456789012345678901234", "checkoutSessionId": "cs_live_abcdef1234567890"})
    test_url = f"https://checkout.stripe.com/c/pay/cs_live_abcdef1234567890#{encoded}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("hit_gate.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp
        mock_session.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session

        res = await hg.qualify_session(test_url)
        assert res["viable"] is True
        assert res["amount_cents"] == 1500
        assert res["currency"] == "USD"
        assert res["three_ds_policy"] == "automatic"
        assert "READY_FOR_HIT" in res["recommendation"]

@pytest.mark.asyncio
async def test_hit_qualify_session_expired():
    mock_payload = {
        "status": "expired",
        "livemode": True,
    }
    encoded = stripe_fid.encode_fragment({"apiKey": "pk_live_123456789012345678901234", "checkoutSessionId": "cs_live_abcdef1234567890"})
    test_url = f"https://checkout.stripe.com/c/pay/cs_live_abcdef1234567890#{encoded}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("hit_gate.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp
        mock_session.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session

        res = await hg.qualify_session(test_url)
        assert res["viable"] is False
        assert res["status"] == "EXPIRED"

@pytest.mark.asyncio
async def test_hit_session_radar_token_injection():
    encoded = stripe_fid.encode_fragment({"apiKey": "pk_live_123456789012345678901234", "checkoutSessionId": "cs_live_abcdef1234567890"})
    test_url = f"https://checkout.stripe.com/c/pay/cs_live_abcdef1234567890#{encoded}"
    sess = hg.CsHitSession(test_url)
    assert sess.hcaptcha_token is None
    assert sess.use_ctoken is False
    sess.hcaptcha_token = "P1_test_radar_token"
    # verify token is stored
    assert sess.hcaptcha_token == "P1_test_radar_token"
