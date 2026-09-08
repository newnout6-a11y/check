from gate_client import extract_turnstile_params, solve_turnstile_url, solve_pow_challenge
from unittest.mock import patch


def test_turnstile_extract_from_container_full():
    html = """
    <html>
    <body>
        <form action="/login" method="POST">
            <div class="cf-turnstile" data-sitekey="0x4AAAAAAAJXexampleKey123"
                 data-action="checkout_login" data-cdata="session_xyz_789"></div>
            <button type="submit">Войти</button>
        </form>
    </body>
    </html>
    """
    res = extract_turnstile_params(html)
    assert res is not None
    assert res["sitekey"] == "0x4AAAAAAAJXexampleKey123"
    assert res["action"] == "checkout_login"
    assert res["cdata"] == "session_xyz_789"


def test_turnstile_extract_from_wrapper_minimal():
    html = '<div class="cf-turnstile-wrapper" data-sitekey="0x4BBBBBBBB123456789"></div>'
    res = extract_turnstile_params(html)
    assert res is not None
    assert res["sitekey"] == "0x4BBBBBBBB123456789"
    assert res["action"] == ""
    assert res["cdata"] == ""


def test_turnstile_extract_from_script_render():
    html = """
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    <div id="target-widget"></div>
    <script>
        window.onloadTurnstileCallback = function () {
            turnstile.render('#target-widget', {
                sitekey: '0x4CCCCCCCCC987654321',
                action: 'payment_submit',
                cData: 'order_ref_4455',
                callback: function(token) {}
            });
        };
    </script>
    """
    res = extract_turnstile_params(html)
    assert res is not None
    assert res["sitekey"] == "0x4CCCCCCCCC987654321"
    assert res["action"] == "payment_submit"
    assert res["cdata"] == "order_ref_4455"


def test_turnstile_extract_global_fallback():
    html = """
    <div>Turnstile protection active</div>
    <input type="text" data-sitekey="0x4DDDDDDDD1122334455" />
    """
    res = extract_turnstile_params(html)
    assert res is not None
    assert res["sitekey"] == "0x4DDDDDDDD1122334455"


def test_turnstile_extract_negative():
    assert extract_turnstile_params("") is None
    assert extract_turnstile_params("<html><body><form></form></body></html>") is None
    assert extract_turnstile_params("Turnstile mentioned in plain text without keys") is None


def test_solve_turnstile_url_mock():
    with patch("turnstile_sidecar.solve_turnstile", return_value="0.dummy_token_123"):
        token = solve_turnstile_url("https://example.com/login")
        assert token == "0.dummy_token_123"

    with patch("turnstile_sidecar.solve_turnstile", side_effect=Exception("browser error")):
        assert solve_turnstile_url("https://example.com/login") is None


def test_solve_pow_challenge_altcha():
    import hashlib
    salt = "salttest"
    sol = 100
    challenge = hashlib.sha256((salt + str(sol)).encode("ascii")).hexdigest()
    c_data = {"challenge": challenge, "salt": salt, "maxnumber": 1000}
    res = solve_pow_challenge(c_data)
    assert res is not None
    assert res["solution"] == sol
    assert "payload" in res

    assert solve_pow_challenge({"invalid": 123}) is None
