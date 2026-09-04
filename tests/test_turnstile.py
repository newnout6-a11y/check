"""Unit-тесты для экстрактора параметров Cloudflare Turnstile (gate_client.extract_turnstile_params)."""
from gate_client import extract_turnstile_params


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
