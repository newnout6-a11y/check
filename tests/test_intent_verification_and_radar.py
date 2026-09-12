# language: Python 3.12+, file: tests/test_intent_verification_and_radar.py, target: Windows 11
import asyncio
import uuid
import pytest

import config
import gate_client as gc
import hit_gate as hg
import stripe_fid


# ============================================================================
# 1. verify_intent_challenge API Contract & Single-Use Rules
# ============================================================================

class MockResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_verify_intent_challenge_success():
    recorded = {}

    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            recorded["url"] = url
            recorded["data"] = data
            recorded["headers"] = headers
            return MockResponse(200, {
                "id": "pi_3Qmock123",
                "object": "payment_intent",
                "status": "requires_confirmation",
                "amount": 5000,
                "currency": "usd",
            })

    session = MockSession()
    res = await gc.verify_intent_challenge(
        session,
        pi_id="pi_3Qmock123",
        pk="pk_live_testmerchantkey",
        client_secret="pi_3Qmock123_secret_xyz",
        challenge_response_token="hcaptcha_solved_token_blob",
        captcha_vendor_name="hcaptcha",
        challenge_response_ekey="ekey_456",
    )

    assert res["status"] == "CHALLENGE_PASSED"
    assert res["http_status"] == 200
    assert res["pi"]["id"] == "pi_3Qmock123"
    assert res["pi"]["status"] == "requires_confirmation"

    assert recorded["url"] == "https://api.stripe.com/v1/payment_intents/pi_3Qmock123/verify_challenge"
    assert recorded["data"]["key"] == "pk_live_testmerchantkey"
    assert recorded["data"]["client_secret"] == "pi_3Qmock123_secret_xyz"
    assert recorded["data"]["challenge_response_token"] == "hcaptcha_solved_token_blob"
    assert recorded["data"]["captcha_vendor_name"] == "hcaptcha"
    assert recorded["data"]["challenge_response_ekey"] == "ekey_456"
    assert recorded["headers"]["Origin"] == "https://js.stripe.com"
    assert recorded["headers"]["Referer"] == "https://js.stripe.com/"
    assert recorded["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


@pytest.mark.asyncio
async def test_verify_intent_challenge_parameter_aliases():
    recorded = {}

    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            recorded["data"] = data
            return MockResponse(200, {"id": "pi_alias", "status": "requires_action"})

    res = await gc.verify_intent_challenge(
        MockSession(),
        pi_id="pi_alias",
        pk="pk_live_test",
        client_secret="secret_123",
        token="token_via_alias",
        vendor="hcaptcha_enterprise",
    )
    assert res["status"] == "CHALLENGE_PASSED"
    assert recorded["data"]["challenge_response_token"] == "token_via_alias"
    assert recorded["data"]["captcha_vendor_name"] == "hcaptcha_enterprise"


@pytest.mark.asyncio
async def test_verify_intent_challenge_burned_by_radar_on_200():
    # Live discovery: Stripe Radar returns HTTP 200 with PI reset to requires_payment_method
    # when challenge token is invalid, rejected or burned.
    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            return MockResponse(200, {
                "id": "pi_burned123",
                "object": "payment_intent",
                "status": "requires_payment_method",
            })

    res = await gc.verify_intent_challenge(
        MockSession(),
        pi_id="pi_burned123",
        pk="pk_live_test",
        client_secret="secret_test",
        challenge_response_token="phony_token",
    )
    assert res["status"] == "CHALLENGE_FAILED"
    assert res["http_status"] == 200
    assert "rejected" in res["detail"] or "requires_payment_method" in res["detail"]


@pytest.mark.asyncio
async def test_verify_intent_challenge_already_burned_error():
    # Subsequent attempt receives 'no valid challenge'
    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            return MockResponse(400, {
                "error": {
                    "code": "challenge_invalid",
                    "message": "There is no valid challenge associated with the current payment attempt.",
                }
            })

    res = await gc.verify_intent_challenge(
        MockSession(),
        pi_id="pi_burned123",
        pk="pk_live_test",
        client_secret="secret_test",
        challenge_response_token="valid_but_late_token",
    )
    assert res["status"] == "CHALLENGE_BURNED"
    assert res["http_status"] == 400
    assert "no valid challenge" in res["detail"].lower()


@pytest.mark.asyncio
async def test_verify_intent_challenge_network_exception():
    class FailingSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            raise asyncio.TimeoutError("verify_challenge timeout")

    res = await gc.verify_intent_challenge(
        FailingSession(),
        pi_id="pi_exc",
        pk="pk_live_test",
        client_secret="sec",
        challenge_response_token="tok",
    )
    assert res["status"] == "ERROR"
    assert "TimeoutError" in res["detail"]


# ============================================================================
# 2. ConfirmationToken (ctoken_...) Lifecycle & Telemetry Isolation
# ============================================================================

def test_confirmation_token_body_isolation_filters_forbidden_fields():
    # Attempting to inject forbidden telemetry fields into ctoken body
    shipping = {
        "name": "Alice Cooper",
        "line1": "123 Rock Road",
        "city": "Detroit",
        "country": "US",
        "guid": "forbidden_guid",
        "muid": "forbidden_muid",
    }
    kwargs_with_telemetry = {
        "guid": "should_be_stripped",
        "muid": "should_be_stripped",
        "sid": "should_be_stripped",
        "payment_user_agent": "should_be_stripped",
        "time_on_page": "42000",
        "custom_allowed_opt": "valid_opt",
    }

    body = gc.confirmation_token_body(
        "pm_test_123",
        "pk_live_test",
        return_url="https://checkout.stripe.com/return",
        shipping=shipping,
        **kwargs_with_telemetry,
    )

    assert body["payment_method"] == "pm_test_123"
    assert body["key"] == "pk_live_test"
    assert body["return_url"] == "https://checkout.stripe.com/return"
    assert body["shipping[name]"] == "Alice Cooper"
    assert body["shipping[line1]"] == "123 Rock Road"
    assert body["custom_allowed_opt"] == "valid_opt"

    # Assert strict telemetry isolation
    for forbidden in gc.FORBIDDEN_CTOKEN_FIELDS:
        assert forbidden not in body
        assert f"shipping[{forbidden}]" not in body


@pytest.mark.asyncio
async def test_create_confirmation_token_network_failure_preserves_pm_id():
    class FailingSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            raise ConnectionResetError("Connection dropped")

    res = await gc.create_confirmation_token(
        FailingSession(),
        pk="pk_live_test",
        pm_id_or_card="pm_fallback_target_123",
    )
    assert res["status"] == "ERROR"
    assert res["pm_id"] == "pm_fallback_target_123"
    assert "ConnectionResetError" in res["detail"]


# ============================================================================
# 3. Telemetry Synthesizer (muid, sid, guid, m cookie & beacon)
# ============================================================================

def test_telemetry_synthesizer_beacon_payload_and_consistency():
    fixed_guid = str(uuid.uuid4())
    fixed_muid = str(uuid.uuid4())
    payload = gc.m_stripe_beacon_payload(url="https://store.example/checkout", guid=fixed_guid, muid=fixed_muid)

    assert payload["v"] == "t"
    assert payload["url"] == "https://store.example/checkout"
    assert payload["guid"] == fixed_guid
    assert payload["muid"] == fixed_muid
    assert len(payload["lsid"]) == 36


def test_parse_m_stripe_response():
    # Valid server response from m.stripe.com/6
    raw_data = {
        "muid": "6d17e766-3d71-4824-a74e-5e730076a520478128",
        "sid": "d652c7be-ee6e-4ff6-8c50-cf32cf05d528b7e0e7",
        "guid": "8c9b3117-0925-4c04-a128-d8f99e4f3a749f7e41",
    }
    parsed = gc.parse_m_stripe_response(raw_data)
    assert parsed["muid"] == raw_data["muid"]
    assert parsed["sid"] == raw_data["sid"]
    assert parsed["guid"] == raw_data["guid"]

    # Truncated or empty values
    empty_parsed = gc.parse_m_stripe_response({"muid": "short", "invalid": 123})
    assert empty_parsed["muid"] == ""
    assert empty_parsed["sid"] == ""


def test_build_stripe_cookies_and_header():
    muid = "6d17e766-3d71-4824-a74e-5e730076a520478128"
    sid = "d652c7be-ee6e-4ff6-8c50-cf32cf05d528b7e0e7"
    cookies = gc.build_stripe_cookies(muid, sid)

    assert cookies["__stripe_mid"] == muid
    assert cookies["__stripe_sid"] == sid
    assert cookies["m"] == muid

    header = gc.format_cookie_header(cookies)
    assert f"__stripe_mid={muid}" in header
    assert f"__stripe_sid={sid}" in header
    assert f"m={muid}" in header


def test_synthesize_telemetry_bundle():
    telem = gc.synthesize_telemetry("https://checkout.example.com", "pk_live_test123", country_code="DE")

    assert telem["key"] == "pk_live_test123"
    assert telem["country"] == "DE"
    assert "muid" in telem and len(telem["muid"]) >= 36
    assert "sid" in telem and len(telem["sid"]) >= 36
    assert "guid" in telem and len(telem["guid"]) >= 36
    assert "payment_user_agent" in telem
    assert "cookies" in telem
    assert telem["cookies"]["__stripe_mid"] == telem["muid"]
    assert telem["cookies"]["__stripe_sid"] == telem["sid"]
    assert telem["cookies"]["m"] == telem["muid"]
    assert "cookie_header" in telem


@pytest.mark.asyncio
async def test_mint_m_stripe_beacon_success_and_fallback():
    # Success scenario
    class GoodBeaconSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            return MockResponse(200, {
                "muid": "11111111-2222-4333-8444-555555555555abcdef",
                "sid": "22222222-3333-4444-8555-666666666666fedcba",
                "guid": "33333333-4444-4555-8666-777777777777123456",
            })

    res = await gc.mint_m_stripe_beacon(GoodBeaconSession())
    assert res["muid"] == "11111111-2222-4333-8444-555555555555abcdef"
    assert res["sid"] == "22222222-3333-4444-8555-666666666666fedcba"
    assert res["cookies"]["__stripe_mid"] == res["muid"]
    assert res["cookies"]["__stripe_sid"] == res["sid"]

    # Fallback scenario on error
    class BadBeaconSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            return MockResponse(500, {"error": "beacon down"})

    fallback_res = await gc.mint_m_stripe_beacon(BadBeaconSession())
    assert len(fallback_res["muid"]) >= 36
    assert len(fallback_res["sid"]) >= 36
    assert fallback_res["cookies"]["__stripe_mid"] == fallback_res["muid"]


# ============================================================================
# 4. Intent Challenge State Machine & In-Flight Resumption in hit_gate.py
# ============================================================================

@pytest.mark.asyncio
async def test_intent_challenge_interception_without_solver():
    session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "encrypted_rqdata_payload",
                    "verification_url": "/v1/payment_intents/pi_3Qmock/verify_challenge",
                }
            }
        }
    }

    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "CAPTCHA_CHECKOUT"
    assert "Radar" in detail
    assert "hCaptcha" in detail
    assert config.is_refundable(verdict) is True


@pytest.mark.asyncio
async def test_intent_challenge_in_flight_resolution_and_resumption_success():
    # End-to-end verification & resumption flow:
    # 1. First confirm returns requires_action + intent_confirmation_challenge.
    # 2. State machine intercepts rqdata, calls challenge_solver.
    # 3. Dispatches to verify_intent_challenge -> returns 200 OK.
    # 4. Resumes confirmation against payment_pages/{cs}/confirm -> returns complete (APPROVED@PAID).

    calls = []

    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            calls.append({"url": url, "data": data})
            if "verify_challenge" in url:
                assert data["challenge_response_token"] == "solved_hcaptcha_token_123"
                assert data["key"] == "pk_live_test123"
                return MockResponse(200, {
                    "id": "pi_3Qchallenge_pi",
                    "status": "requires_confirmation",
                })
            if "payment_pages/cs_live_test123/confirm" in url:
                return MockResponse(200, {
                    "status": "complete",
                    "payment_status": "paid",
                    "payment_intent": {"id": "pi_3Qchallenge_pi", "status": "succeeded"},
                })
            return MockResponse(404, {"error": "not found"})

    solver_called = {}

    async def mock_solver(site_key, rqdata, verification_url, url):
        solver_called["site_key"] = site_key
        solver_called["rqdata"] = rqdata
        solver_called["verification_url"] = verification_url
        return "solved_hcaptcha_token_123"

    session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test123#fid", challenge_solver=mock_solver)
    session.s = MockSession()
    session.pk = "pk_live_test123"
    session.cs = "cs_live_test123"
    session.pi_id = "pi_3Qchallenge_pi"
    session.secret = "pi_3Qchallenge_pi_secret_abc"
    session.amount = 2500
    session.currency = "USD"

    initial_challenge_resp = {
        "payment_intent": {
            "id": "pi_3Qchallenge_pi",
            "status": "requires_action",
            "client_secret": "pi_3Qchallenge_pi_secret_abc",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "test_rqdata_blob_abc",
                    "verification_url": "/v1/payment_intents/pi_3Qchallenge_pi/verify_challenge",
                }
            }
        }
    }

    verdict, detail = await session._classify_and_resolve_3ds(initial_challenge_resp)

    # Verification and resumption assertions
    assert solver_called["site_key"] == "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"
    assert solver_called["rqdata"] == "test_rqdata_blob_abc"
    assert solver_called["verification_url"] == "/v1/payment_intents/pi_3Qchallenge_pi/verify_challenge"

    # Should achieve terminal resolution to APPROVED@PAID
    assert verdict == "APPROVED@PAID"
    assert "checkout complete" in detail or "PI succeeded" in detail

    # Both verify_challenge and resumed confirm must have been dispatched
    assert any("verify_challenge" in c["url"] for c in calls)
    assert any("payment_pages/cs_live_test123/confirm" in c["url"] for c in calls)


@pytest.mark.asyncio
async def test_intent_challenge_verification_rejected_falls_back_to_captcha_checkout():
    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            if "verify_challenge" in url:
                # Radar burns the token: 200 with reset to requires_payment_method
                return MockResponse(200, {
                    "id": "pi_3Q_failed",
                    "status": "requires_payment_method",
                })
            return MockResponse(200, {})

    async def mock_solver(site_key, rqdata, verification_url, url):
        return "bad_token"

    session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test123#fid", challenge_solver=mock_solver)
    session.s = MockSession()
    session.pk = "pk_live_test123"
    session.cs = "cs_live_test123"
    session.pi_id = "pi_3Q_failed"
    session.secret = "sec"

    resp = {
        "payment_intent": {
            "id": "pi_3Q_failed",
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "rq",
                }
            }
        }
    }

    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "CAPTCHA_CHECKOUT"
    assert "verification failed" in detail.lower()
    assert config.is_refundable(verdict) is True


@pytest.mark.asyncio
async def test_intent_challenge_solver_exception_clean_classification():
    async def broken_solver(**kwargs):
        raise RuntimeError("Solver API key exhausted")

    session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test123#fid", challenge_solver=broken_solver)
    session.s = MockResponse(200, {})

    resp = {
        "payment_intent": {
            "status": "requires_action",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "rq",
                }
            }
        }
    }
    verdict, detail = await session._classify_and_resolve_3ds(resp)
    assert verdict == "CAPTCHA_CHECKOUT"
    assert config.is_refundable(verdict) is True


@pytest.mark.asyncio
async def test_hit_session_ctoken_lifecycle_and_fallback():
    ctoken_created = False
    confirm_body_received = {}

    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            nonlocal ctoken_created
            if "payment_methods" in url:
                return MockResponse(200, {"id": "pm_card_minted_123"})
            if "confirmation_tokens" in url:
                ctoken_created = True
                return MockResponse(200, {"id": "ctoken_live_minted_456", "object": "confirmation_token"})
            if "payment_pages" in url and "confirm" in url:
                confirm_body_received.update(data)
                return MockResponse(200, {"status": "complete", "payment_status": "paid"})
            return MockResponse(404, {})

        async def get(self, url, params=None, headers=None, timeout=None):
            return MockResponse(200, {"status": "open", "payment_intent": {"status": "requires_payment_method"}})

    # Run check_card with use_ctoken=True
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid", use_ctoken=True)
    sess.s = MockSession()
    sess.pk = "pk_live_test"
    sess.cs = "cs_live_test"
    sess.amount = 1000
    sess.currency = "USD"

    res = await sess.check_card("5175465382242090|09|2030|018")
    assert ctoken_created is True
    assert confirm_body_received.get("confirmation_token") == "ctoken_live_minted_456"
    assert "payment_method" not in confirm_body_received
    assert res["status"] == "APPROVED@PAID"

    # Run check_card with use_ctoken=True but confirmation_token creation failure -> fallback to pm_...
    confirm_body_fallback = {}

    class MockFailingCtokenSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            if "payment_methods" in url:
                return MockResponse(200, {"id": "pm_fallback_ok_789"})
            if "confirmation_tokens" in url:
                return MockResponse(400, {"error": {"code": "parameter_unknown", "message": "Unsupported mode"}})
            if "payment_pages" in url and "confirm" in url:
                confirm_body_fallback.update(data)
                return MockResponse(200, {"status": "complete", "payment_status": "paid"})
            return MockResponse(404, {})

        async def get(self, url, params=None, headers=None, timeout=None):
            return MockResponse(200, {"status": "open", "payment_intent": {"status": "requires_payment_method"}})

    sess_fallback = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid", use_ctoken=True)
    sess_fallback.s = MockFailingCtokenSession()
    sess_fallback.pk = "pk_live_test"
    sess_fallback.cs = "cs_live_test"
    sess_fallback.amount = 1000
    sess_fallback.currency = "USD"

    res_fb = await sess_fallback.check_card("5175465382242090|09|2030|018")
    assert confirm_body_fallback.get("payment_method") == "pm_fallback_ok_789"
    assert "confirmation_token" not in confirm_body_fallback
    assert res_fb["status"] == "APPROVED@PAID"


@pytest.mark.asyncio
async def test_execute_hit_integration_with_ctoken_and_settlement(monkeypatch):
    class MockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            if "payment_methods" in url:
                return MockResponse(200, {"id": "pm_exec_hit"})
            if "confirmation_tokens" in url:
                return MockResponse(200, {"id": "ctoken_exec_hit", "object": "confirmation_token"})
            if "confirm" in url:
                return MockResponse(200, {"status": "complete", "payment_status": "paid"})
            return MockResponse(404, {})

        async def get(self, url, params=None, headers=None, timeout=None):
            return MockResponse(200, {
                "status": "open",
                "payment_intent": {
                    "id": "pi_exec_hit",
                    "status": "requires_payment_method",
                    "amount": 1500,
                    "currency": "usd",
                }
            })

        async def close(self):
            pass

    test_frag = stripe_fid.encode_fragment({"apiKey": "pk_live_test123", "checkoutSessionId": "cs_live_test123"})
    test_url = f"https://checkout.stripe.com/c/pay/cs_live_test123#{test_frag}"

    monkeypatch.setattr(hg, "AsyncSession", lambda **kwargs: MockSession())

    out = await hg.execute_hit(test_url, ["5175465382242090|09|2030|018"], use_ctoken=True)
    assert out["pipeline"] == "SUCCESS"
    assert out["status"] in config.VERDICTS
    assert out["viable"] is True
    assert out["terminal_hit"] is not None
    assert out["terminal_hit"]["status"] == "APPROVED@PAID"
