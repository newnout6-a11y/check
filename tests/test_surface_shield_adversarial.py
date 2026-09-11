# language: Python 3.12+, file: tests/test_surface_shield_adversarial.py, target: Windows 11
"""
Adversarial Stress Test Suite for surface_shield.py
Milestone 1 - Challenger Verification Matrix
Tests tricky boundary conditions, deceptive HTML, false-positive resistance, and regex stability.
"""
import time
import pytest
import surface_shield as ss

# =====================================================================
# 1. CRITICAL: HTTP 200 Active Challenge Interstitial Discrimination
# =====================================================================

def test_adv_http_200_cloudflare_challenge_interstitial_detected():
    """
    Adversarial Scenario: Cloudflare served an active Managed Challenge / Turnstile
    interstitial under HTTP 200 (common with custom CF rules).
    Page title is 'Just a moment...' and challenge-platform script is present.
    Bug in code: BLOCK_TITLES has leading '<title>' so BLOCK_TITLES.search(effective_title) fails.
    Must be detected as is_active_block == True!
    """
    html = '''<!DOCTYPE html>
    <html>
      <head><title>Just a moment...</title></head>
      <body>
        <script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>
        <div id="challenge-running">Please stand by while we verify your browser.</div>
      </body>
    </html>'''
    res = ss.classify_protection(200, {"server": "cloudflare"}, "", html)
    assert res["is_active_block"] is True, f"Failed: HTTP 200 challenge interstitial was marked as passive (block={res['is_active_block']})"
    assert res["waf"] == "cloudflare"
    assert "turnstile" in res["bypass_strategy"] or "sidecar" in res["bypass_strategy"]

def test_adv_http_200_datadome_interstitial_detected():
    """
    Adversarial Scenario: DataDome returns HTTP 200 interstitial page (not 403)
    with title 'Attention Required' and captcha-delivery iframe.
    Must be detected as is_active_block == True.
    """
    html = '''<html>
      <head><title>Attention Required! | Cloudflare</title></head>
      <body>
        <iframe src="https://geo.captcha-delivery.com/captcha/?initialCid=123"></iframe>
      </body>
    </html>'''
    res = ss.classify_protection(200, {"server": "datadome"}, "", html)
    assert res["is_active_block"] is True
    assert res["bypass_strategy"] == "residential_proxy_rotation"


# =====================================================================
# 2. BOUNDARY CONDITIONS: Type Safety & Corrupted Inputs
# =====================================================================

def test_adv_boundary_none_html_resilience():
    """
    Adversarial Scenario: Upstream library returns None for empty response body.
    classify_protection and inspect_form_protections must handle None without crashing.
    """
    res = ss.classify_protection(200, headers={}, cookies="", html=None)
    assert res["status_code"] == 200
    assert res["is_active_block"] is False

    fp = ss.inspect_form_protections(None)
    assert fp["has_woocommerce_nonce"] is False

def test_adv_boundary_non_string_keys_headers_cookies():
    """
    Adversarial Scenario: Malformed headers/cookies dictionary with integer or byte keys.
    classify_protection must coerce or safely handle non-string keys without unhandled exceptions.
    """
    headers = {123: "val", "server": "nginx"}
    cookies = {456: "session_val", "cf_clearance": "tok123"}
    res = ss.classify_protection(200, headers=headers, cookies=cookies, html="<html></html>")
    assert res["waf"] == "cloudflare"

def test_adv_boundary_empty_strings_and_missing_keys():
    """
    Adversarial Scenario: Completely empty input parameters across all fields.
    """
    res = ss.classify_protection(0, headers={}, cookies="", html="", page_title="")
    assert res["waf"] == "none"
    assert res["is_active_block"] is False
    assert res["form_protections"]["has_woocommerce_nonce"] is False


# =====================================================================
# 3. NONCE EXTRACTION: Attribute Order Inversions
# =====================================================================

def test_adv_nonce_extraction_attribute_order_inverted():
    """
    Adversarial Scenario: HTML tags where 'value' attribute precedes 'name' or 'id'.
    Common in CMS themes, React/Vue SSR, or minified HTML.
    Current regex fails because it strictly expects name/id before value!
    """
    html = '''
    <form class="checkout woocommerce-checkout">
      <!-- value before name -->
      <input type="hidden" value="8a1b2c3d4e" name="woocommerce-register-nonce" />
      <input type="hidden" value="1234567890" name="_wpnonce" />
      <input type="hidden" value="abcdef0123" name="woocommerce-process-checkout-nonce" />
    </form>
    '''
    fp = ss.inspect_form_protections(html)
    assert fp["has_woocommerce_nonce"] is True
    assert fp["nonces"]["woocommerce_register_nonce"] == "8a1b2c3d4e", "Failed to extract register nonce when value precedes name"
    assert fp["nonces"]["wpnonce"] == "1234567890", "Failed to extract wpnonce when value precedes name"
    assert fp["nonces"]["checkout_nonce"] == "abcdef0123", "Failed to extract checkout nonce when value precedes name"


# =====================================================================
# 4. DECEPTIVE HTML: Shield Substring False Positives
# =====================================================================

def test_adv_script_signature_no_false_positive_on_common_words():
    r"""
    Adversarial Scenario: A completely legitimate website bundles a script named
    'tips.js', 'clips.js', or 'recipes.js'.
    Current regex r'(kpsdk|ips\.js|...)' matches 'tips.js' and falsely identifies Kasada WAF & Kasada PoW!
    """
    html = '''
    <html>
      <head><title>Kitchen Tips</title><script src="/assets/js/tips.js"></script></head>
      <body><h1>Great kitchen tips</h1></body>
    </html>
    '''
    res = ss.classify_protection(200, {"server": "nginx"}, "", html)
    assert "kasada" not in res["shields"], f"False positive: 'tips.js' triggered Kasada shield: {res['shields']}"
    assert "kasada_pow" not in res["shields"]
    assert res["waf"] != "kasada"

def test_adv_altcha_link_in_footer_does_not_override_bypass_strategy():
    """
    Adversarial Scenario: A blog or store has a link to 'altcha.org' in its privacy policy
    or footer text, but has NO actual altcha widget.
    Current code searches 'altcha.org' in html -> triggers has_pow=True -> sets bypass_strategy='captcha_pow_cpu'!
    """
    html = '''
    <html>
      <head><title>Shoe Store</title></head>
      <body class="woocommerce-checkout">
        <form class="checkout woocommerce-checkout">
          <input type="hidden" name="_wpnonce" value="1234567890" />
        </form>
        <footer>Learn about bot security at https://altcha.org</footer>
      </body>
    </html>
    '''
    res = ss.classify_protection(200, {"server": "nginx"}, "", html)
    assert res["bypass_strategy"] != "captcha_pow_cpu", f"False override: altcha link forced bypass_strategy to {res['bypass_strategy']}"


# =====================================================================
# 5. HONEYPOT & ACCOUNT BARRIER: Discrimination Accuracy
# =====================================================================

def test_adv_honeypot_does_not_flag_legitimate_hidden_inputs():
    """
    Adversarial Scenario: Standard WooCommerce checkout forms contain hidden inputs
    like billing_state, shipping_address_2 (pre-filled), or nonce fields with style="display:none".
    Current regex RE_HIDDEN_HONEYPOT_INPUTS flags ANY input with display:none!
    """
    html = '''
    <form class="woocommerce-checkout">
      <input type="text" name="billing_country" value="US" />
      <input type="text" name="billing_state" style="display:none;" value="NY" />
      <input type="hidden" name="woocommerce-process-checkout-nonce" style="display:none;" value="1234567890" />
    </form>
    '''
    fp = ss.inspect_form_protections(html)
    assert "billing_state" not in fp["honeypots"], f"billing_state flagged as honeypot: {fp['honeypots']}"
    assert "woocommerce-process-checkout-nonce" not in fp["honeypots"], f"nonce flagged as honeypot: {fp['honeypots']}"

def test_adv_account_barrier_no_false_positive_on_faq_discussion():
    """
    Adversarial Scenario: Page text discusses account creation or checkout terms:
    'You must be logged in to checkout if you want member points, but guest checkout is welcome!'
    Current regex matches 'You must be logged in to checkout' anywhere in the DOM.
    """
    html = '''
    <html>
      <head><title>Artisan Coffee Checkout</title></head>
      <body class="woocommerce-checkout">
        <div class="faq-accordion">
          <p>You must be logged in to checkout with points, but guest checkout is open to everyone.</p>
        </div>
        <form class="checkout woocommerce-checkout" action="/checkout">
          <input type="hidden" name="_wpnonce" value="1234567890" />
          <button type="submit">Place Order as Guest</button>
        </form>
      </body>
    </html>
    '''
    fp = ss.inspect_form_protections(html)
    # If guest checkout is actively present on the page, account barrier must be false
    # or should strictly match container elements (<div class="woocommerce-must-be-logged-in">)
    assert fp["has_account_barrier"] is False, "False positive: Account barrier flagged on explanatory FAQ text"
