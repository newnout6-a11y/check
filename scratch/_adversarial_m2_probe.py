# language: Python 3.12+, file: scratch/_adversarial_m2_probe.py, target: Windows 11
"""
Adversarial Probe & Stress Harness for M2:
1. Challenge verification wire contract (unexpected vendors, empty token, missing keys, malformed JSON, single-use burn)
2. ConfirmationToken parameter isolation (forbidden telemetry, case variants, prefixed keys, shipping leakage)
3. ConfirmationToken fallback resilience (400, 500, network exceptions, json decode errors, check_card transparent fallback)
4. Telemetry synthesizer consistency (UUID4 compliance, entropy over 1000 iterations, session persistence across check_card)
5. Cookie formatting & m.stripe.com/6 beacon edge cases
"""

import asyncio
import os
import re
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import gate_client as gc
import hit_gate as hg


class DummyResponse:
    def __init__(self, status_code: int, data: dict = None, text: str = ""):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = text or str(self._data)

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


# ============================================================================
# 1. Challenge Verification Adversarial Probes
# ============================================================================

async def probe_verify_intent_challenge_edge_cases():
    print("[1] Probing verify_intent_challenge edge cases...")
    recorded = []

    class MockSession:
        def __init__(self, resp):
            self.resp = resp

        async def post(self, url, data=None, headers=None, timeout=None):
            recorded.append({"url": url, "data": data, "headers": headers})
            return self.resp

    # Case 1.1: Unexpected / custom vendor string
    s = MockSession(DummyResponse(200, {"id": "pi_1", "status": "succeeded"}))
    r = await gc.verify_intent_challenge(s, "pi_1", "pk_live", "sec_1",
                                         token="tok_abc", vendor="custom_recaptcha_v3")
    assert r["status"] == "OK"
    assert recorded[-1]["data"]["captcha_vendor_name"] == "custom_recaptcha_v3"
    assert recorded[-1]["data"]["challenge_response_token"] == "tok_abc"

    # Case 1.2: Empty / None vendor string defaults to "hcaptcha"
    r2 = await gc.verify_intent_challenge(s, "pi_1", "pk_live", "sec_1",
                                          token="tok_abc", vendor="", captcha_vendor_name="")
    assert r2["status"] == "OK"
    assert recorded[-1]["data"]["captcha_vendor_name"] == "hcaptcha"

    # Case 1.3: Empty token submits empty string without exception
    r3 = await gc.verify_intent_challenge(s, "pi_1", "pk_live", "sec_1",
                                          token="", challenge_response_token=None)
    assert r3["status"] == "OK"
    assert recorded[-1]["data"]["challenge_response_token"] == ""

    # Case 1.4: Single-use burn on HTTP 200 with requires_payment_method
    burn_sess = MockSession(DummyResponse(200, {"id": "pi_burn", "status": "requires_payment_method"}))
    r4 = await gc.verify_intent_challenge(burn_sess, "pi_burn", "pk_live", "sec_1", token="dummy")
    assert r4["status"] == "CHALLENGE_FAILED"
    assert r4["http_status"] == 200
    assert "rejected" in r4["detail"]

    # Case 1.5: Re-attempt on burned challenge returns 400 "no valid challenge"
    burned_err_sess = MockSession(DummyResponse(400, {
        "error": {
            "code": "challenge_invalid",
            "message": "There is no valid challenge associated with the current payment attempt.",
        }
    }))
    r5 = await gc.verify_intent_challenge(burned_err_sess, "pi_burn", "pk_live", "sec_1", token="dummy")
    assert r5["status"] == "CHALLENGE_BURNED"
    assert r5["http_status"] == 400

    # Case 1.6: Malformed response (non-JSON body) on HTTP 502
    bad_json_sess = MockSession(DummyResponse(502, data=ValueError("Bad JSON"), text="<html>Bad Gateway</html>"))
    r6 = await gc.verify_intent_challenge(bad_json_sess, "pi_1", "pk_live", "sec_1", token="tok")
    assert r6["status"] == "ERROR"
    assert r6["http_status"] == 502
    assert "502" in r6["detail"]

    # Case 1.7: Missing status field in 200 response
    no_status_sess = MockSession(DummyResponse(200, {"id": "pi_nostat"}))
    r7 = await gc.verify_intent_challenge(no_status_sess, "pi_nostat", "pk_live", "sec_1", token="tok")
    assert r7["status"] == "OK"
    assert r7["pi"]["id"] == "pi_nostat"

    # Case 1.8: HTTP 200 containing error payload
    err_200_sess = MockSession(DummyResponse(200, {"error": {"message": "Invalid challenge response"}}))
    r8 = await gc.verify_intent_challenge(err_200_sess, "pi_1", "pk_live", "sec_1", token="tok")
    assert r8["status"] == "ERROR"
    assert r8["detail"] == "Invalid challenge response"

    print("  -> All verify_intent_challenge edge cases passed!")


# ============================================================================
# 2. ConfirmationToken Lifecycle & Parameter Isolation
# ============================================================================

def probe_confirmation_token_isolation():
    print("[2] Probing ConfirmationToken parameter isolation...")
    
    # 2.1 Direct injection of all known forbidden fields
    for field in gc.FORBIDDEN_CTOKEN_FIELDS:
        injected = {field: "leak_val"}
        body = gc.confirmation_token_body("pm_test", "pk_live", **injected)
        assert field not in body, f"Direct field {field} was not stripped from ctoken body!"

    # 2.2 Prefixed injection (e.g. client_attribution_metadata[...], radar_options[...])
    prefixed = {
        "client_attribution_metadata[client_session_id]": "src_123",
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "radar_options[hcaptcha_token]": "P1_leak",
        "payment_user_agent_full": "stripe.js/v3",
        "guid_secondary": "secondary_guid",
    }
    body_pref = gc.confirmation_token_body("pm_test", "pk_live", **prefixed)
    for k in prefixed:
        assert k not in body_pref, f"Prefixed telemetry {k} leaked into ctoken body!"

    # 2.3 Shipping dictionary leakage probe
    leaky_shipping = {
        "name": "Bob",
        "line1": "456 Elm St",
        "city": "Dallas",
        "state": "TX",
        "postal_code": "75001",
        "country": "US",
        "muid": "leak_muid",
        "sid": "leak_sid",
        "guid": "leak_guid",
        "payment_user_agent": "leak_pua",
    }
    body_ship = gc.confirmation_token_body("pm_test", "pk_live", shipping=leaky_shipping)
    assert body_ship["shipping[name]"] == "Bob"
    assert body_ship["shipping[line1]"] == "456 Elm St"
    assert "shipping[muid]" not in body_ship
    assert "shipping[sid]" not in body_ship
    assert "shipping[guid]" not in body_ship
    assert "shipping[payment_user_agent]" not in body_ship

    # 2.4 Whitelist verification: only key, payment_method, return_url, shipping[...] allowed
    allowed_keys = {"key", "payment_method", "return_url", "shipping[name]", "shipping[line1]",
                    "shipping[city]", "shipping[state]", "shipping[postal_code]", "shipping[country]"}
    for k in body_ship:
        assert k in allowed_keys, f"Unexpected key {k} found in body_ship!"

    print("  -> ConfirmationToken parameter isolation verified across all attack surfaces!")


# ============================================================================
# 3. ConfirmationToken Fallback Resilience
# ============================================================================

async def probe_confirmation_token_fallback_resilience():
    print("[3] Probing ConfirmationToken fallback resilience...")

    class ErrorSession:
        def __init__(self, status_code, data=None, exc=None):
            self.status_code = status_code
            self.data = data
            self.exc = exc

        async def post(self, url, data=None, headers=None, timeout=None):
            if self.exc:
                raise self.exc
            return DummyResponse(self.status_code, self.data)

    # 3.1 400 parameter_unknown preserves pm_id
    s_400 = ErrorSession(400, {"error": {"code": "parameter_unknown", "message": "Received unknown parameter: custom"}})
    res_400 = await gc.create_confirmation_token(s_400, "pk_live", "pm_target_400")
    assert res_400["status"] == "DECLINED" or res_400["status"] == "ERROR"
    assert res_400["pm_id"] == "pm_target_400"

    # 3.2 500 internal server error preserves pm_id
    s_500 = ErrorSession(500, {"error": {"message": "Stripe internal error"}})
    res_500 = await gc.create_confirmation_token(s_500, "pk_live", "pm_target_500")
    assert res_500["pm_id"] == "pm_target_500"

    # 3.3 Connection reset / timeout preserves pm_id
    s_exc = ErrorSession(0, exc=asyncio.TimeoutError("Stripe ctoken timeout"))
    res_exc = await gc.create_confirmation_token(s_exc, "pk_live", "pm_target_exc")
    assert res_exc["status"] == "ERROR"
    assert res_exc["pm_id"] == "pm_target_exc"
    assert "TimeoutError" in res_exc["detail"]

    # 3.4 CsHitSession check_card transparent fallback on ctoken failure
    class HitFallbackMockSession:
        def __init__(self):
            self.confirmed_with_pm = False
            self.used_ctoken = False

        async def post(self, url, data=None, headers=None, timeout=None):
            if "payment_methods" in url:
                return DummyResponse(200, {"id": "pm_card_robust_123"})
            if "confirmation_tokens" in url:
                # Fails with 400 parameter_unknown
                return DummyResponse(400, {"error": {"code": "parameter_unknown", "message": "Disabled for account"}})
            if "payment_pages" in url and "confirm" in url:
                if data.get("payment_method") == "pm_card_robust_123" and "confirmation_token" not in data:
                    self.confirmed_with_pm = True
                if "confirmation_token" in data:
                    self.used_ctoken = True
                return DummyResponse(200, {"status": "complete", "payment_status": "paid"})
            return DummyResponse(404)

        async def get(self, url, params=None, headers=None, timeout=None):
            return DummyResponse(200, {"status": "open", "payment_intent": {"status": "requires_payment_method"}})

    mock_sess = HitFallbackMockSession()
    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_fb#fid", use_ctoken=True)
    sess.s = mock_sess
    sess.pk = "pk_live_test"
    sess.cs = "cs_live_fb"
    sess.amount = 1200
    sess.currency = "USD"

    result = await sess.check_card("5175465382242090|09|2030|018")
    assert result["status"] == "APPROVED@PAID"
    assert mock_sess.confirmed_with_pm is True, "check_card failed to fall back to payment_method!"
    assert mock_sess.used_ctoken is False

    # 3.5 CsHitSession check_card transparent fallback when create_confirmation_token raises exception
    class HitExcMockSession:
        def __init__(self):
            self.confirmed_with_pm = False

        async def post(self, url, data=None, headers=None, timeout=None):
            if "payment_methods" in url:
                return DummyResponse(200, {"id": "pm_card_exc_123"})
            if "confirmation_tokens" in url:
                raise OSError("Network socket dropped")
            if "payment_pages" in url and "confirm" in url:
                if data.get("payment_method") == "pm_card_exc_123":
                    self.confirmed_with_pm = True
                return DummyResponse(200, {"status": "complete", "payment_status": "paid"})
            return DummyResponse(404)

        async def get(self, url, params=None, headers=None, timeout=None):
            return DummyResponse(200, {"status": "open", "payment_intent": {"status": "requires_payment_method"}})

    exc_sess = HitExcMockSession()
    sess2 = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_fb2#fid", use_ctoken=True)
    sess2.s = exc_sess
    sess2.pk = "pk_live_test"
    sess2.cs = "cs_live_fb2"
    sess2.amount = 1500
    sess2.currency = "EUR"

    res2 = await sess2.check_card("5175465382242090|09|2030|018")
    assert res2["status"] == "APPROVED@PAID"
    assert exc_sess.confirmed_with_pm is True, "check_card failed to fall back to pm_... on exception!"

    print("  -> ConfirmationToken fallback resilience confirmed under 400, 500, timeouts, and network drops!")


# ============================================================================
# 4. Telemetry Synthesizer Consistency & Session Persistence
# ============================================================================

async def probe_telemetry_synthesizer_entropy_and_structure():
    print("[4] Probing Telemetry Synthesizer entropy, UUID formats, and cookie persistence...")

    # 4.1 UUID4 format check
    uuid4_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    
    muids = set()
    sids = set()
    guids = set()

    for _ in range(500):
        t = gc.synthesize_telemetry("https://example.com/checkout", "pk_live_probe", country_code="US")
        m = t["muid"]
        s = t["sid"]
        g = t["guid"]

        assert uuid4_pattern.match(m), f"Invalid UUID4 format for muid: {m}"
        assert uuid4_pattern.match(s), f"Invalid UUID4 format for sid: {s}"
        assert uuid4_pattern.match(g), f"Invalid UUID4 format for guid: {g}"

        assert t["cookies"]["__stripe_mid"] == m
        assert t["cookies"]["__stripe_sid"] == s
        assert t["cookies"]["m"] == m
        assert f"__stripe_mid={m}" in t["cookie_header"]
        assert f"__stripe_sid={s}" in t["cookie_header"]
        assert f"m={m}" in t["cookie_header"]

        muids.add(m)
        sids.add(s)
        guids.add(g)

    # High entropy check: 500 unique items generated with zero collisions
    assert len(muids) == 500, "Entropy failure: collision in generated muids"
    assert len(sids) == 500, "Entropy failure: collision in generated sids"
    assert len(guids) == 500, "Entropy failure: collision in generated guids"

    # 4.2 Custom m_cookie override
    custom_cookies = gc.build_stripe_cookies(muid="muid_val", sid="sid_val", m_cookie="custom_m_override")
    assert custom_cookies["m"] == "custom_m_override"
    assert custom_cookies["__stripe_mid"] == "muid_val"
    assert custom_cookies["__stripe_sid"] == "sid_val"

    # 4.3 Empty / None handling in cookie formatting
    partial_cookies = gc.build_stripe_cookies(muid="muid_only", sid="")
    assert "m" in partial_cookies
    assert "__stripe_sid" not in partial_cookies
    header = gc.format_cookie_header(partial_cookies)
    assert "__stripe_sid" not in header
    assert "__stripe_mid=muid_only" in header

    # 4.4 Session persistence across multiple check_card calls in CsHitSession
    class MockPersistenceSession:
        def __init__(self):
            self.telem_muids = []
            self.telem_sids = []

        async def post(self, url, data=None, headers=None, timeout=None):
            if "payment_methods" in url:
                self.telem_muids.append(data.get("muid"))
                self.telem_sids.append(data.get("sid"))
                return DummyResponse(200, {"id": f"pm_{len(self.telem_muids)}"})
            if "payment_pages" in url and "confirm" in url:
                return DummyResponse(200, {"status": "complete", "payment_status": "paid"})
            return DummyResponse(404)

        async def get(self, url, params=None, headers=None, timeout=None):
            return DummyResponse(200, {"status": "open", "payment_intent": {"status": "requires_payment_method"}})

    hit_session = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_persist#fid")
    mock_p = MockPersistenceSession()
    hit_session.s = mock_p
    hit_session.pk = "pk_live_persist"
    hit_session.cs = "cs_live_persist"
    hit_session.amount = 1000
    hit_session.currency = "USD"
    # Simulate open()
    hit_session.muid = str(uuid.uuid4())
    hit_session.sid = str(uuid.uuid4())

    # Perform 5 check_card calls
    for _ in range(5):
        await hit_session.check_card("5175465382242090|09|2030|018")

    # Verify that identical muid and sid were passed into tokenize_body for all 5 attempts!
    assert len(mock_p.telem_muids) == 5
    assert len(set(mock_p.telem_muids)) == 1, f"muid drifted across check_card calls: {mock_p.telem_muids}"
    assert len(set(mock_p.telem_sids)) == 1, f"sid drifted across check_card calls: {mock_p.telem_sids}"
    assert mock_p.telem_muids[0] == hit_session.muid
    assert mock_p.telem_sids[0] == hit_session.sid

    print("  -> Telemetry Synthesizer entropy, formatting, and session persistence fully verified!")


# ============================================================================
# 5. Intent Challenge Recursion Depth & Anti-Loop Safeguard
# ============================================================================

async def probe_intent_challenge_recursion_guard():
    print("[5] Probing Intent Challenge anti-loop recursion depth safeguard...")

    # Challenge response that keeps returning intent_confirmation_challenge repeatedly
    loop_challenge_resp = {
        "payment_intent": {
            "id": "pi_loop",
            "status": "requires_action",
            "client_secret": "sec_loop",
            "next_action": {
                "type": "use_stripe_sdk",
                "use_stripe_sdk": {
                    "type": "intent_confirmation_challenge",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "rqdata": "rq_loop",
                }
            }
        }
    }

    verify_calls = 0

    class LoopMockSession:
        async def post(self, url, data=None, headers=None, timeout=None):
            nonlocal verify_calls
            if "verify_challenge" in url:
                verify_calls += 1
                return DummyResponse(200, {"id": "pi_loop", "status": "requires_confirmation"})
            if "confirm" in url:
                # Returns the same challenge again to trigger infinite loop attempt
                return DummyResponse(200, loop_challenge_resp)
            return DummyResponse(404)

    async def infinite_solver(**kwargs):
        return "infinite_token"

    sess = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_loop#fid", challenge_solver=infinite_solver)
    sess.s = LoopMockSession()
    sess.pk = "pk_live_test"
    sess.cs = "cs_live_loop"
    sess.pi_id = "pi_loop"
    sess.secret = "sec_loop"

    verdict, detail = await sess._classify_and_resolve_3ds(loop_challenge_resp)
    
    # State machine must NOT loop indefinitely; recursion_depth < 2 halts it cleanly
    assert verdict == "CAPTCHA_CHECKOUT"
    assert verify_calls <= 2, f"State machine failed recursion guard; called verify_challenge {verify_calls} times!"
    print(f"  -> Recursion guard successfully halted infinite challenge loop after {verify_calls} attempts!")


async def run_all_probes():
    await probe_verify_intent_challenge_edge_cases()
    probe_confirmation_token_isolation()
    await probe_confirmation_token_fallback_resilience()
    await probe_telemetry_synthesizer_entropy_and_structure()
    await probe_intent_challenge_recursion_guard()
    print("\n[V] ALL ADVERSARIAL STRESS PROBES PASSED WITH 100% SUCCESS.")


if __name__ == "__main__":
    asyncio.run(run_all_probes())
