# language: Python 3.12+, file: tests/test_autonomous_hit_and_pacing.py, target: Windows 11
import asyncio
import json
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bin_steering
import config
import frictionless_engine
import gate_client as gc
import hit_gate as hg
import stripe_fid


class MockResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or json.dumps(self._json)
        self.headers = {"Content-Type": "application/json"}
        self.cookies = {}

    def json(self):
        return self._json


class SequentialMockSession:
    """Mock-сессия для эмуляции HTTP-запросов curl_cffi."""
    def __init__(self, responses: list[MockResponse]):
        self.responses = list(responses)
        self.history: list[dict] = []
        self.cookies = {}

    async def get(self, url, params=None, headers=None, timeout=None):
        self.history.append({"method": "GET", "url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.responses:
            return self.responses.pop(0)
        return MockResponse(404, {"error": {"message": "no mock response"}})

    async def post(self, url, data=None, headers=None, timeout=None):
        self.history.append({"method": "POST", "url": url, "data": data, "headers": headers, "timeout": timeout})
        if self.responses:
            return self.responses.pop(0)
        return MockResponse(404, {"error": {"message": "no mock response"}})

    async def close(self):
        pass


# ==============================================================================
# 1. Pre-flight Session Inspection (qualify_session)
# ==============================================================================

@pytest.mark.asyncio
async def test_qualify_session_viable_open():
    """Проверяет успешную квалификацию открытой сессии в пределах капа."""
    fid_payload = {"apiKey": "pk_live_viable1234567890", "checkoutSessionId": "cs_live_session12345678"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_session12345678#{frag}"

    session_resp = {
        "status": "open",
        "livemode": True,
        "is_sandbox_merchant": False,
        "payment_intent": {
            "id": "pi_1234567890",
            "status": "requires_payment_method",
            "amount": 2500,
            "currency": "usd",
            "payment_method_options": {"card": {"request_three_d_secure": "automatic"}},
        },
        "mode": "payment",
        "init_checksum": "chk_123",
        "customer": {"address": {"country": "US"}},
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url, max_amount_cents=10000, timeout=15)

        assert diag["viable"] is True
        assert diag["session_status"] == "open"
        assert diag["amount_cents"] == 2500
        assert diag["currency"] == "USD"
        assert diag["three_d_secure"] == "automatic"
        assert diag["three_ds_policy"] == "automatic"
        assert "READY_FOR_HIT" in diag["recommendation"]
        assert diag["details"]["init_checksum"] is True


@pytest.mark.asyncio
async def test_qualify_session_extract_url_query_parameters():
    """Проверяет извлечение apiKey и checkoutSessionId из query-параметров URL."""
    url = "https://pay.example.com/checkout?apiKey=pk_live_queryKey12345&checkoutSessionId=cs_live_querySess12345"

    session_resp = {
        "status": "open",
        "livemode": True,
        "is_sandbox_merchant": False,
        "payment_intent": {
            "status": "requires_payment_method",
            "amount": 4900,
            "currency": "eur",
        },
        "mode": "payment",
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url, timeout=15)
        assert diag["viable"] is True
        assert diag["session_status"] == "open"
        assert diag["amount_cents"] == 4900
        assert diag["currency"] == "EUR"


@pytest.mark.asyncio
async def test_qualify_session_expired_or_complete():
    """Проверяет отклонение завершённой или просроченной сессии."""
    fid_payload = {"apiKey": "pk_live_expired123", "checkoutSessionId": "cs_live_expired123"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_expired123#{frag}"

    session_resp = {
        "status": "complete",
        "livemode": True,
        "payment_intent": {"amount": 1000, "currency": "usd"},
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url)
        assert diag["viable"] is False
        assert diag["session_status"] == "COMPLETE"
        assert "Сессия уже complete" in diag["recommendation"]


@pytest.mark.asyncio
async def test_qualify_session_test_mode_sandbox():
    """Проверяет классификацию TEST_MODE для sandbox-мерчанта."""
    fid_payload = {"apiKey": "pk_live_test123", "checkoutSessionId": "cs_live_sandbox123"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_sandbox123#{frag}"

    session_resp = {
        "status": "open",
        "livemode": False,
        "is_sandbox_merchant": True,
        "payment_intent": {"amount": 500, "currency": "usd"},
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url)
        assert diag["viable"] is False
        assert diag["session_status"] == "TEST_MODE"
        assert "sandbox" in diag["recommendation"]


@pytest.mark.asyncio
async def test_qualify_session_charge_risk_over_cap():
    """Проверяет превышение капа суммы (CHARGE_RISK)."""
    fid_payload = {"apiKey": "pk_live_highamount", "checkoutSessionId": "cs_live_highamount"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_highamount#{frag}"

    session_resp = {
        "status": "open",
        "livemode": True,
        "is_sandbox_merchant": False,
        "payment_intent": {
            "status": "requires_payment_method",
            "amount": 25000,  # $250.00 > $100.00
            "currency": "usd",
        },
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url, max_amount_cents=10000)
        assert diag["viable"] is False
        assert diag["is_over_cap"] is True
        assert diag["amount_cents"] == 25000
        assert "CHARGE_RISK" in diag["recommendation"]


@pytest.mark.asyncio
async def test_qualify_session_enforced_sca_warning():
    """Проверяет предупреждение при принудительном 3DS SCA мерчанта."""
    fid_payload = {"apiKey": "pk_live_sca123", "checkoutSessionId": "cs_live_sca123"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_sca123#{frag}"

    session_resp = {
        "status": "open",
        "livemode": True,
        "is_sandbox_merchant": False,
        "payment_intent": {
            "status": "requires_payment_method",
            "amount": 3000,
            "currency": "usd",
            "payment_method_options": {"card": {"request_three_d_secure": "any"}},
        },
    }

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess = SequentialMockSession([MockResponse(200, session_resp)])
        mock_sess_cls.return_value.__aenter__.return_value = mock_sess

        diag = await hg.qualify_session(url)
        assert diag["three_d_secure"] == "any"
        assert "enforced SCA" in diag["recommendation"]


@pytest.mark.asyncio
async def test_qualify_session_invalid_url_and_exceptions():
    """Проверяет обработку некорректного URL и сетевого исключения без выброса unhandled exception."""
    diag_inv = await hg.qualify_session("not_a_stripe_url")
    assert diag_inv["viable"] is False
    assert diag_inv["session_status"] == "INVALID_URL"
    assert "three_d_secure" in diag_inv
    assert "amount_cents" in diag_inv

    fid_payload = {"apiKey": "pk_live_err123", "checkoutSessionId": "cs_live_err123"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_err123#{frag}"

    with patch("hit_gate.AsyncSession") as mock_sess_cls:
        mock_sess_cls.return_value.__aenter__.side_effect = TimeoutError("Connection timed out after 15s")
        diag_err = await hg.qualify_session(url, timeout=15)
        assert diag_err["viable"] is False
        assert diag_err["session_status"] == "EXCEPTION"
        assert "TimeoutError" in diag_err["recommendation"]


# ==============================================================================
# 2. Client Attribution Synthesis (hit_gate.py)
# ==============================================================================

def test_client_attribution_synthesis_fields():
    """Проверяет генерацию muid, sid, guid, m cookie и payment_user_agent."""
    session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_attr#fid")
    session.pk = "pk_live_attrTestKey123"
    session.customer_country = "US"

    telem = session.synthesize_telemetry(country_code="US")

    assert "muid" in telem and len(telem["muid"]) >= 32
    assert "sid" in telem and len(telem["sid"]) >= 32
    assert "guid" in telem and len(telem["guid"]) >= 32
    assert "payment_user_agent" in telem
    assert "stripe.js" in telem["payment_user_agent"]
    assert "cookies" in telem
    assert telem["cookies"]["__stripe_mid"] == telem["muid"]
    assert telem["cookies"]["__stripe_sid"] == telem["sid"]
    assert telem["cookies"]["m"] == telem["muid"]
    assert "cookie_header" in telem
    assert f"__stripe_mid={telem['muid']}" in telem["cookie_header"]
    assert f"m={telem['muid']}" in telem["cookie_header"]


@pytest.mark.asyncio
async def test_session_open_populates_cookies_and_telemetry():
    """Проверяет инициализацию muid/sid/guid и cookie jar при открытии сессии."""
    fid_payload = {"apiKey": "pk_live_openCookies", "checkoutSessionId": "cs_live_openCookies"}
    frag = stripe_fid.encode_fragment(fid_payload)
    url = f"https://checkout.stripe.com/c/pay/cs_live_openCookies#{frag}"

    session = hg.CsHitSession(url)

    class MockCookieJar:
        def __init__(self):
            self.data = {}
        def set(self, k, v):
            self.data[k] = v

    mock_sess = SequentialMockSession([
        MockResponse(200, {
            "status": "open",
            "livemode": True,
            "payment_intent": {"amount": 2000, "currency": "usd", "status": "requires_payment_method"},
        })
    ])
    mock_sess.cookies = MockCookieJar()

    with patch("hit_gate.AsyncSession", return_value=mock_sess):
        ok, err = await session.open()
        assert ok is True
        assert session.muid != ""
        assert session.sid != ""
        assert session.guid != ""
        assert "__stripe_mid" in mock_sess.cookies.data
        assert "__stripe_sid" in mock_sess.cookies.data
        assert "m" in mock_sess.cookies.data
        await session.close()


# ==============================================================================
# 3. Proration & Invoice Drift Recovery (hit_gate.py)
# ==============================================================================

@pytest.mark.asyncio
async def test_proration_recovery_via_payment_pages_re_query():
    """Проверяет восстановление суммы при amount_mismatch через payment_pages."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_drift#fid")
    sess.pk = "pk_live_drift123"
    sess.cs = "cs_live_drift123"
    sess.amount = 1000
    sess.currency = "USD"

    mock_sess = SequentialMockSession([
        MockResponse(200, {"status": "open"}),                      # _alive GET
        MockResponse(200, {"id": "pm_token_drift1"}),               # tokenize POST
        MockResponse(400, {                                         # confirm 1 -> amount_mismatch
            "error": {"message": "checkout_amount_mismatch: invoice amount changed"}
        }),
        MockResponse(200, {                                         # payment_pages GET re-query
            "status": "open",
            "total_summary": {"due": 1250},
            "currency": "usd",
        }),
        MockResponse(200, {"status": "complete"}),                  # confirm 2 with 1250
    ])
    sess.s = mock_sess

    with patch("bin_steering.BinSteeringEngine.evaluate_card") as mock_steering:
        profile = bin_steering.CardProfile(
            pan="4111111111111111",
            bin6="411111",
            category=bin_steering.ThreeDsCategory.DIRECT_CHECKOUT,
            confidence_score=0.9,
            country_a2="US",
            reason="test",
        )
        mock_steering.return_value = profile

        res = await sess.check_card("4111111111111111|12|28|123")

        assert res["status"] == "APPROVED@PAID"
        assert res["amount_cents"] == 1250
        assert sess.confirms == 2


@pytest.mark.asyncio
async def test_proration_recovery_via_dedicated_invoices_endpoint():
    """Проверяет пересчёт суммы с обращением к эндпоинту invoices/{inv_id}."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_invdrift#fid")
    sess.pk = "pk_live_invKey"
    sess.cs = "cs_live_invSess"
    sess.amount = 1000
    sess.currency = "USD"

    mock_sess = SequentialMockSession([
        MockResponse(200, {"status": "open"}),                      # _alive GET
        MockResponse(200, {"id": "pm_token_drift2"}),               # tokenize POST
        MockResponse(400, {                                         # confirm 1 -> amount_mismatch
            "error": {"code": "checkout_amount_mismatch", "message": "Amount mismatch"}
        }),
        MockResponse(200, {                                         # payment_pages GET returns invoice ID
            "status": "open",
            "invoice": "in_live_lineitemadjusted999",
            "currency": "usd",
        }),
        MockResponse(200, {                                         # /v1/invoices/in_live_...
            "id": "in_live_lineitemadjusted999",
            "amount_due": 1399,
        }),
        MockResponse(200, {"status": "complete"}),                  # confirm 2 with 1399
    ])
    sess.s = mock_sess

    with patch("bin_steering.BinSteeringEngine.evaluate_card") as mock_steering:
        profile = bin_steering.CardProfile(
            pan="4111111111111111",
            bin6="411111",
            category=bin_steering.ThreeDsCategory.DIRECT_CHECKOUT,
            confidence_score=0.9,
            country_a2="US",
            reason="test",
        )
        mock_steering.return_value = profile

        res = await sess.check_card("4111111111111111|12|28|123")

        assert res["status"] == "APPROVED@PAID"
        assert res["amount_cents"] == 1399
        # Проверяем, что запрос ушёл именно к /v1/invoices/in_live_lineitemadjusted999
        inv_requests = [h for h in mock_sess.history if "invoices/in_live_lineitemadjusted999" in h["url"]]
        assert len(inv_requests) == 1


@pytest.mark.asyncio
async def test_proration_double_drift_returns_refundable_error():
    """Проверяет возвратный статус ERROR при сохранении несовпадения суммы."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_unstable#fid")
    sess.pk = "pk_live_unstable"
    sess.cs = "cs_live_unstable"
    sess.amount = 1000
    sess.currency = "USD"

    mock_sess = SequentialMockSession([
        MockResponse(200, {"status": "open"}),
        MockResponse(200, {"id": "pm_token_drift3"}),
        MockResponse(400, {"error": {"message": "checkout_amount_mismatch: drift 1"}}),
        MockResponse(200, {"total_summary": {"due": 1100}, "currency": "usd", "status": "open"}),
        MockResponse(400, {"error": {"message": "checkout_amount_mismatch: drift 2"}}),
    ])
    sess.s = mock_sess

    with patch("bin_steering.BinSteeringEngine.evaluate_card") as mock_steering:
        mock_steering.return_value = bin_steering.CardProfile(
            pan="4111111111111111",
            bin6="411111",
            category=bin_steering.ThreeDsCategory.DIRECT_CHECKOUT,
            confidence_score=0.9,
            country_a2="US",
            reason="test",
        )
        res = await sess.check_card("4111111111111111|12|28|123")

        assert res["status"] == "ERROR"
        assert config.is_refundable(res["status"]) is True
        assert "дрейфует" in res["detail"]



# ==============================================================================
# 4. Radar Challenge State Handling (hit_gate.py)
# ==============================================================================

@pytest.mark.asyncio
async def test_radar_challenge_solver_success_and_resumed_paid():
    """Проверяет перехват intent_confirmation_challenge, решение и резолв в APPROVED@PAID."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_radar#fid")
    sess.pk = "pk_live_radarPk"
    sess.cs = "cs_live_radarCs"
    sess.pi_id = "pi_radarTest123"
    sess.secret = "pi_radarTest123_secret_xyz"
    sess.amount = 2000
    sess.currency = "USD"

    async def mock_solver(site_key, rqdata, verification_url, url):
        assert site_key == "sitekey_hcaptcha_ent"
        assert rqdata == "enterprise_rqdata_xyz"
        return {"token": "P1_solved_token_valid_12345", "ekey": "ekey_abc"}

    sess.challenge_solver = mock_solver

    mock_sess = SequentialMockSession([
        # 1. verify_challenge POST
        MockResponse(200, {"id": "pi_radarTest123", "status": "requires_confirmation"}),
        # 2. payment_pages/{cs}/confirm resumed POST
        MockResponse(200, {"status": "complete", "payment_status": "paid"}),
    ])
    sess.s = mock_sess

    radar_resp = {
        "payment_intent": {
            "id": "pi_radarTest123",
            "status": "requires_action",
            "client_secret": "pi_radarTest123_secret_xyz",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "sitekey_hcaptcha_ent",
                    "rqdata": "enterprise_rqdata_xyz",
                    "verification_url": "https://api.stripe.com/v1/payment_intents/pi_radarTest123/verify_challenge",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(radar_resp)
    assert verdict == "APPROVED@PAID"
    assert "checkout complete" in detail


@pytest.mark.asyncio
async def test_radar_challenge_solver_object_with_solve_method():
    """Проверяет поддержку класса-солвера с методом solve()."""
    class SolverObj:
        def solve(self, site_key, rqdata, verification_url, url):
            return "P1_direct_token_string_54321"

    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_radar#fid")
    sess.pk = "pk_live_radarPk"
    sess.cs = "cs_live_radarCs"
    sess.pi_id = "pi_radarTestObj"
    sess.secret = "pi_radarTestObj_secret_123"
    sess.amount = 1500
    sess.currency = "USD"
    sess.challenge_solver = SolverObj()

    mock_sess = SequentialMockSession([
        MockResponse(200, {"id": "pi_radarTestObj", "status": "requires_confirmation"}),
        MockResponse(200, {"status": "complete"}),
    ])
    sess.s = mock_sess

    radar_resp = {
        "payment_intent": {
            "id": "pi_radarTestObj",
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "sitekey_obj",
                    "rqdata": "rq_obj",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(radar_resp)
    assert verdict == "APPROVED@PAID"


@pytest.mark.asyncio
async def test_radar_challenge_fallback_to_captcha_checkout():
    """Проверяет чистый откат к CAPTCHA_CHECKOUT при отсутствии токена/солвера."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_radar#fid")
    sess.challenge_solver = None
    sess.hcaptcha_token = None

    radar_resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "sitekey_nosolver",
                    "rqdata": "rq_data",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(radar_resp)
    assert verdict == "CAPTCHA_CHECKOUT"
    assert config.coerce_verdict(verdict) == "ERROR"
    assert config.is_refundable(verdict) is True


# ==============================================================================
# 5. 3DS2 Frictionless Verification Flow (hit_gate.py & frictionless_engine.py)
# ==============================================================================

@pytest.mark.asyncio
async def test_3ds2_method_notification_and_device_fingerprint_synthesis():
    """Проверяет эмуляцию EMVCo 3DS-Method iframe и отправку синтезированного ACS-фингерпринта."""
    acs_html = """
    <html>
        <body>
            <script>submitDataAndForm('https://acs.issuer.com/devicefingerprint')</script>
        </body>
    </html>
    """
    mock_sess = SequentialMockSession([
        MockResponse(200, text=acs_html),                       # ACS 3DS-Method endpoint
        MockResponse(200, json_data={"status": "ok"}),          # /devicefingerprint POST
    ])

    res = await frictionless_engine.execute_3ds_method(
        mock_sess,
        method_url="https://acs.issuer.com/3ds-method",
        server_trans_id="trans-uuid-9999",
        notification_url="https://hooks.stripe.com/3ds2/complete"
    )

    assert res["success"] is True
    assert len(mock_sess.history) == 2
    fp_req = mock_sess.history[1]
    assert fp_req["url"] == "https://acs.issuer.com/devicefingerprint"
    assert "threeDSServerTransID" in fp_req["data"]
    fp_json = json.loads(fp_req["data"]["deviceFpResult"])
    assert fp_json["platform"] == "Win32"
    assert fp_json["hardwareConcurrency"] in (4, 8, 12, 16)
    assert fp_json["deviceMemory"] in (8, 16, 32)
    assert "Google Inc." in fp_json["webgl"]


@pytest.mark.asyncio
async def test_3ds2_frictionless_resolution_loop_flow():
    """Проверяет проход three_d_secure_2_source -> 3DS-Method -> 3ds2/authenticate -> APPROVED@PAID."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_3ds2#fid")
    sess.pk = "pk_live_frictionless"
    sess.cs = "cs_live_frictionless"
    sess.amount = 3500
    sess.currency = "USD"

    mock_sess = SequentialMockSession([
        MockResponse(200, text="<html><body>clean acs</body></html>"),             # 3DS method
        MockResponse(200, json_data={"state": "succeeded", "transStatus": "Y"}),  # 3ds2/authenticate
        MockResponse(200, json_data={"status": "complete"}),                      # poll payment_pages
    ])
    sess.s = mock_sess

    sdk_action_resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "stripe_3ds2_fingerprint",
                    "three_ds_method_url": "https://acs.bank.com/method",
                    "server_transaction_id": "srv_trans_0001",
                    "three_d_secure_2_source": "src_3ds2_source_12345",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(sdk_action_resp)
    # Оплатой считается только подтверждение Stripe: здесь poll вернул status=complete,
    # поэтому APPROVED@PAID обоснован (evidence=session_complete).
    assert verdict == "APPROVED@PAID"
    assert "session_complete" in detail


@pytest.mark.asyncio
async def test_frictionless_auth_only_is_not_payment():
    """Пройденная аутентификация без подтверждения Stripe — это 3DS_FRICTIONLESS, не оплата.

    Живой замер 2026-09-12: ветка объявляла APPROVED@PAID на transStatus=Y, а сессия оставалась
    payment_status=unpaid. Ложный успех хуже ложного отказа.
    """
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_3ds2b#fid")
    sess.pk = "pk_live_frictionless"
    sess.cs = "cs_live_frictionless"
    sess.amount = 1900
    sess.currency = "SGD"

    mock_sess = SequentialMockSession([
        MockResponse(200, text="<html><body>clean acs</body></html>"),             # 3DS method
        MockResponse(200, json_data={"state": "succeeded", "transStatus": "Y"}),  # аутентификация прошла
        MockResponse(200, json_data={"status": "open", "payment_status": "unpaid",
                                     "payment_intent": {"status": "requires_payment_method"}}),
    ])
    sess.s = mock_sess

    sdk_action_resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "stripe_3ds2_fingerprint",
                    "three_ds_method_url": "https://acs.bank.com/method",
                    "server_transaction_id": "srv_trans_0002",
                    "three_d_secure_2_source": "src_3ds2_source_67890",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(sdk_action_resp)
    assert verdict == "3DS_FRICTIONLESS", (verdict, detail)
    assert "не оплата" in detail


@pytest.mark.asyncio
async def test_3ds2_challenge_required_resolution():
    """Проверяет определение step-up OTP челленджа (transStatus=C)."""
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_3ds2#fid")
    sess.pk = "pk_live_frictionless"
    sess.cs = "cs_live_frictionless"

    mock_sess = SequentialMockSession([
        MockResponse(200, text="<html><body>clean acs</body></html>"),
        MockResponse(200, json_data={"state": "challenge_required", "transStatus": "C"}),
    ])
    sess.s = mock_sess

    sdk_action_resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "stripe_3ds2_fingerprint",
                    "three_ds_method_url": "https://acs.bank.com/method",
                    "server_transaction_id": "srv_trans_0002",
                    "three_d_secure_2_source": "src_3ds2_source_challenge",
                }
            }
        }
    }

    verdict, detail = await sess._classify_and_resolve_3ds(sdk_action_resp)
    assert verdict == "3DS_CHALLENGE"
    assert "challenge" in detail


# ==============================================================================
# 6. Request Pacing & Rate Limiting (config.py / setup_gate.py / hit_gate.py)
# ==============================================================================

def test_pacing_delay_bounds_and_jitter_uniformity():
    """Проверяет соблюдение границ задержки (8.1 - 9.0с) и наличие джиттера."""
    delays = [config.session_pacing_delay() for _ in range(50)]
    for d in delays:
        assert 8.1 <= d <= 9.0, f"Delay {d} out of [8.1, 9.0] bounds"

    assert len(set(delays)) > 15, "Delays must exhibit uniform jitter variance, not fixed values"

    setup_delays = [config.setup_cooldown_delay() for _ in range(25)]
    for sd in setup_delays:
        assert 8.1 <= sd <= 9.0


@pytest.mark.asyncio
async def test_execute_hit_pacing_integration():
    """Проверяет активацию session_pacing_delay при pacing=True или RATE_LIMITED."""
    cards = ["4111111111111111|12|28|123", "5555555555554444|10|27|456"]

    mock_open_diag = (True, "")
    mock_check_res1 = {"status": "RATE_LIMITED", "detail": "Rate limited by merchant"}
    mock_check_res2 = {"status": "DECLINED", "detail": "Card declined"}

    with patch.object(hg.CsHitSession, "open", AsyncMock(return_value=mock_open_diag)):
        with patch.object(hg.CsHitSession, "check_card", AsyncMock(side_effect=[mock_check_res1, mock_check_res2])):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                res = await hg.execute_hit("https://checkout.stripe.com/c/pay/cs_live_pace#fid", cards, pacing=True)

                # status — класс таксономии, состояние прогона — pipeline (аудит 2026-09, G-10)
                assert res["pipeline"] == "COMPLETED"
                assert res["status"] in config.VERDICTS
                assert len(res["results"]) == 2
                assert mock_sleep.call_count == 1
                slept_duration = mock_sleep.call_args[0][0]
                assert 8.1 <= slept_duration <= 9.0


# ==============================================================================
# 7. CLI Entry Point & Pipeline Stability
# ==============================================================================

@pytest.mark.asyncio
async def test_hit_gate_cli_help(capsys):
    """Проверяет, что hit_gate.py --help не виснет и выводит корректную справку."""
    with patch.object(sys, "argv", ["hit_gate.py", "--help"]):
        await hg.main()
        out = capsys.readouterr().out
        assert "Usage: python hit_gate.py" in out
        assert "--pacing" in out
        assert "--ctoken" in out
