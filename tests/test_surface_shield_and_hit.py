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

def test_surface_shield_fastly_detection():
    headers = {"server": "fastly", "x-fastly-request-id": "req-12345", "fastly-restarts": "1"}
    res = ss.classify_protection(200, headers, "", "<html><title>Fastly Site</title><body>Content</body></html>")
    assert res["waf"] == "fastly"
    assert res["waf_confidence"] >= 0.90
    assert any("fastly" in ev.lower() for ev in res["waf_evidence"])
    assert res["is_active_block"] is False
    assert res["bypass_strategy"] == "standard_direct"

def test_surface_shield_aws_waf_detection():
    headers = {"x-amzn-waf-action": "block", "x-amzn-requestid": "amzn-req-999"}
    cookies = "aws-waf-token=tok_aws_sec_123;"
    res = ss.classify_protection(403, headers, cookies, "<html><title>Access Denied</title><body>AWS WAF Block</body></html>")
    assert res["waf"] == "aws_waf"
    assert res["is_active_block"] is True
    assert res["bypass_strategy"] == "warm_session_harvest"

def test_surface_shield_imperva_detection():
    headers = {"x-iinfo": "12-34-56", "x-cdn": "Imperva Incapsula"}
    cookies = {"incap_ses_123": "sess_val_1", "visid_incap_456": "vis_val_2"}
    res = ss.classify_protection(200, headers, cookies, "<html><title>Store Home</title></html>")
    assert res["waf"] == "imperva"
    assert res["waf_confidence"] >= 0.90
    assert res["is_active_block"] is False

def test_surface_shield_kasada_detection():
    headers = {"x-kpsdk-ct": "kpsdk_ct_token", "x-kpsdk-cd": "kpsdk_cd_data"}
    cookies = "KP_UIDz=uid_kasada_999;"
    res = ss.classify_protection(200, headers, cookies, "<html><title>Kasada Protected App</title></html>")
    assert res["waf"] == "kasada"
    assert res["waf_confidence"] >= 0.90

def test_surface_shield_recaptcha_v2_v3_detection():
    html_v2 = '''
    <html>
      <head><title>Form Page</title><script src="https://www.google.com/recaptcha/api.js"></script></head>
      <body>
        <div class="g-recaptcha" data-sitekey="6Ld12345678901234567890123456789012345678"></div>
      </body>
    </html>
    '''
    res_v2 = ss.classify_protection(200, {}, "", html_v2)
    assert "recaptcha" in res_v2["shields"]
    assert res_v2["sitekeys"]["recaptcha"] == "6Ld12345678901234567890123456789012345678"
    assert res_v2["is_active_block"] is False
    assert res_v2["bypass_strategy"] == "direct_api_or_recaptcha_v3"

    html_v3 = '''
    <html>
      <head><title>Modern Store</title>
      <script src="https://www.google.com/recaptcha/api.js?render=6Le12345678901234567890123456789012345678"></script>
      </head>
      <body><p>Clean shop</p></body>
    </html>
    '''
    res_v3 = ss.classify_protection(200, {}, "", html_v3)
    assert "recaptcha" in res_v3["shields"]
    assert res_v3["sitekeys"]["recaptcha"] == "6Le12345678901234567890123456789012345678"

def test_surface_shield_hcaptcha_enterprise_detection():
    html = '''
    <html>
      <head>
        <script src="https://hcaptcha.com/1/api.js?checksiteconfig=1" async defer></script>
      </head>
      <body>
        <div class="h-captcha" data-sitekey="c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"></div>
      </body>
    </html>
    '''
    res = ss.classify_protection(200, {}, "", html)
    assert "hcaptcha" in res["shields"]
    assert "hcaptcha_enterprise" in res["shields"]
    assert res["sitekeys"]["hcaptcha"] == "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"
    assert res["bypass_strategy"] == "silent_radar_token_or_ctoken"
    assert res["is_active_block"] is False

def test_surface_shield_datadome_slider_and_interstitial():
    html_slider = '''
    <html>
      <head><title>Attention Required</title></head>
      <body>
        <div id="datadome-slider"></div>
        <script src="https://geo.captcha-delivery.com/captcha/?initialCid=12345"></script>
      </body>
    </html>
    '''
    res = ss.classify_protection(403, {"server": "datadome"}, "datadome=test_val", html_slider)
    assert res["waf"] == "datadome"
    assert "datadome_slider" in res["shields"]
    assert res["is_active_block"] is True
    assert res["bypass_strategy"] == "residential_proxy_rotation"

def test_surface_shield_kasada_pow_detection():
    html_pow = '''
    <html>
      <head>
        <script src="/ips.js"></script>
        <script>window.KPSDK = { version: "1.0" };</script>
      </head>
      <body>
        <p>Kasada Proof of Work</p>
      </body>
    </html>
    '''
    res = ss.classify_protection(429, {"x-kpsdk-ct": "active_challenge"}, "KP_UIDz=uid123", html_pow)
    assert res["waf"] == "kasada"
    assert "kasada_pow" in res["shields"]
    assert res["is_active_block"] is True
    assert res["bypass_strategy"] == "patchright_headless_eval"

def test_surface_shield_form_protections_woocommerce_nonces():
    html = '''
    <form class="checkout woocommerce-checkout">
      <input type="hidden" id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="8a1b2c3d4e" />
      <input type="hidden" id="_wpnonce" name="_wpnonce" value="1234567890" />
      <input type="hidden" id="woocommerce-process-checkout-nonce" name="woocommerce-process-checkout-nonce" value="abcdef0123" />
    </form>
    '''
    headers = {"X-WC-Store-API-Nonce": "fedcba9876"}
    res = ss.classify_protection(200, headers, "", html, page_title="Checkout – Artisan Store")
    fp = res["form_protections"]
    assert fp["has_woocommerce_nonce"] is True
    assert fp["nonces"]["woocommerce_register_nonce"] == "8a1b2c3d4e"
    assert fp["nonces"]["wpnonce"] == "1234567890"
    assert fp["nonces"]["checkout_nonce"] == "abcdef0123"
    assert fp["nonces"]["store_api_nonce"] == "fedcba9876"

def test_surface_shield_form_protections_honeypots():
    html = '''
    <form method="post" action="/checkout">
      <input type="text" name="billing_first_name" value="John" />
      <input type="text" style="display:none;" name="wpa_field" value="" />
      <input type="text" name="wc_register_hp" style="visibility:hidden" value="" />
    </form>
    '''
    fp = ss.inspect_form_protections(html)
    assert fp["has_honeypot"] is True
    assert "wpa_field" in fp["honeypots"]
    assert "wc_register_hp" in fp["honeypots"]

    # Clean form without honeypots
    clean_html = '<form><input type="text" name="name" /><input type="hidden" name="_wpnonce" value="1234567890" /></form>'
    clean_fp = ss.inspect_form_protections(clean_html)
    assert clean_fp["has_honeypot"] is False
    assert len(clean_fp["honeypots"]) == 0

def test_surface_shield_form_protections_account_barriers():
    # WP-Members restriction
    html_wpmem = '''
    <div class="wpmem_msg">You must be logged in to view this content.</div>
    <form id="wpmem_login">
      <input type="text" name="log" />
    </form>
    '''
    fp_wpmem = ss.inspect_form_protections(html_wpmem)
    assert fp_wpmem["has_account_barrier"] is True
    assert fp_wpmem["account_barrier_type"] == "wp_members"

    # WooCommerce mandatory login
    html_must_login = '''
    <div class="woocommerce-must-be-logged-in">
      <p class="must-log-in">You must be logged in to checkout.</p>
    </div>
    '''
    fp_must_login = ss.inspect_form_protections(html_must_login)
    assert fp_must_login["has_account_barrier"] is True
    assert fp_must_login["account_barrier_type"] == "must_be_logged_in"

    # Clean guest checkout
    html_clean = '<form name="checkout" class="woocommerce-checkout"><p>Guest checkout enabled</p></form>'
    fp_clean = ss.inspect_form_protections(html_clean)
    assert fp_clean["has_account_barrier"] is False
    assert fp_clean["account_barrier_type"] is None

def test_surface_shield_checkout_page_zero_false_positive():
    """Legitimate checkout page with embedded bot telemetry must yield is_active_block == False."""
    checkout_html = '''
    <html>
      <head>
        <title>Checkout – Nordic Roast Coffee</title>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
        <script src="https://www.google.com/recaptcha/api.js" async defer></script>
        <script src="https://js.datadome.co/tags.js" async></script>
        <script src="/sensor.js"></script>
      </head>
      <body class="woocommerce-checkout">
        <form name="checkout" class="checkout woocommerce-checkout" action="/checkout">
          <input type="hidden" id="_wpnonce" name="_wpnonce" value="a1b2c3d4e5" />
          <input type="hidden" id="woocommerce-process-checkout-nonce" name="woocommerce-process-checkout-nonce" value="f6e5d4c3b2" />
          <div class="cf-turnstile-wrapper" data-sitekey="0x4AAAAAAtestSiteKey"></div>
          <div class="g-recaptcha" data-sitekey="6Ld12345678901234567890123456789012345678"></div>
          <button type="submit">Place Order</button>
        </form>
      </body>
    </html>
    '''
    headers = {"server": "cloudflare", "cf-ray": "999abcdef0123456-IAD"}
    cookies = "cf_clearance=valid_cf_clearance_tok; _abck=valid_akamai_cookie; _dd_s=1;"
    res = ss.classify_protection(200, headers, cookies, checkout_html, page_title="Checkout – Nordic Roast Coffee")

    assert res["status_code"] == 200
    assert res["waf"] == "cloudflare"
    assert res["is_active_block"] is False  # Zero False Positive guarantee!
    assert res["bypass_strategy"] == "direct_api_or_turnstile_sidecar"
    assert "cloudflare_turnstile" in res["shields"]
    assert "recaptcha" in res["shields"]
    assert "datadome" in res["shields"]
    assert "akamai" in res["shields"]
    assert res["sitekeys"]["turnstile"] == "0x4AAAAAAtestSiteKey"
    assert res["form_protections"]["has_woocommerce_nonce"] is True
    assert res["form_protections"]["has_account_barrier"] is False

def test_surface_shield_inspect_target_sla_timeout_default():
    """Verify inspect_target default timeout is aligned with <2.0s SLA requirement."""
    import inspect
    sig = inspect.signature(ss.inspect_target)
    assert sig.parameters["timeout"].default == 2.0

@pytest.mark.asyncio
async def test_surface_shield_inspect_target_session_mock():
    """Verify inspect_target calls AsyncSession with default 2.0s timeout and parses response correctly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_headers = MagicMock()
    mock_headers.items.return_value = [("server", "cloudflare"), ("cf-ray", "8e1234567890abcd-IAD")]
    mock_headers.get.side_effect = lambda k, d="": {"server": "cloudflare", "cf-ray": "8e1234567890abcd-IAD"}.get(k, d)
    mock_headers.get_list.return_value = ["cf_clearance=xyz123"]
    mock_resp.headers = mock_headers
    mock_resp.text = '<html><head><title>Organic Store</title></head><body>Welcome</body></html>'
    mock_resp.url = "https://organic-store.com"

    with patch("surface_shield.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_resp
        mock_session.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session

        profile = await ss.inspect_target("https://organic-store.com")
        assert profile["alive"] is True
        assert profile["waf"] == "cloudflare"
        assert profile["is_active_block"] is False
        mock_session.get.assert_called_once()
        _, kwargs = mock_session.get.call_args
        assert kwargs.get("timeout") == 2.0

@pytest.mark.asyncio
async def test_surface_shield_inspect_target_timeout_handling():
    """Verify inspect_target handles timeout gracefully and returns non-fatal diagnostic report."""
    with patch("surface_shield.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.get.side_effect = TimeoutError("Connection timed out after 2.0s")
        mock_session.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session

        profile = await ss.inspect_target("https://slow-target.com", timeout=2.0)
        assert profile["alive"] is False
        assert "TimeoutError" in profile["error"]
        assert profile["is_active_block"] is False
        assert profile["bypass_strategy"] == "retry_with_fresh_proxy"

@pytest.mark.asyncio
async def test_hit_qualify_session_invalid_url():
    res = await hg.qualify_session("https://example.com/not-a-stripe-link")
    assert res["viable"] is False
    assert res["session_status"] == "INVALID_URL"

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
        assert res["session_status"] == "EXPIRED"

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
