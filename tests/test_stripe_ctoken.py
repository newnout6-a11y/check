# language: Python 3.12+, file: tests/test_stripe_ctoken.py, target: Windows 11
# Тесты Stripe Confirmation Token (ctoken_...) интеграции (2026).
import pytest
import gate_client as gc
import config


def test_confirmation_token_body_structure():
    body = gc.confirmation_token_body("pm_12345", "pk_live_test", return_url="https://store.test/return")
    assert body["payment_method"] == "pm_12345"
    assert body["key"] == "pk_live_test"
    assert body["return_url"] == "https://store.test/return"

    # v1/confirmation_tokens строго отвергает устаревшие телеметрические поля
    for forbidden in ("payment_user_agent", "guid", "muid", "sid"):
        assert forbidden not in body


def test_confirmation_token_body_shipping():
    shipping = {
        "name": "Jane Doe",
        "line1": "10 Downing St",
        "city": "London",
        "country": "GB",
    }
    body = gc.confirmation_token_body("pm_999", "pk_live_test", shipping=shipping)
    assert body["shipping[name]"] == "Jane Doe"
    assert body["shipping[line1]"] == "10 Downing St"
    assert body["shipping[city]"] == "London"
    assert body["shipping[country]"] == "GB"


@pytest.mark.asyncio
async def test_create_confirmation_token_from_pm():
    class DummyResponse:
        status_code = 200
        def json(self):
            return {
                "id": "ctoken_test_abc123",
                "object": "confirmation_token",
                "livemode": True,
            }

    class DummySession:
        async def post(self, url, data=None, headers=None, timeout=None):
            assert url == "https://api.stripe.com/v1/confirmation_tokens"
            assert data["payment_method"] == "pm_live_xyz"
            assert data["key"] == "pk_live_test"
            return DummyResponse()

    res = await gc.create_confirmation_token(DummySession(), "pk_live_test", "pm_live_xyz")
    assert res["status"] == "OK"
    assert res["id"] == "ctoken_test_abc123"
    assert res["pm_id"] == "pm_live_xyz"


@pytest.mark.asyncio
async def test_create_confirmation_token_from_card():
    posted_urls = []

    class DummyResponsePM:
        status_code = 200
        def json(self):
            return {"id": "pm_auto_minted_456"}

    class DummyResponseCT:
        status_code = 200
        def json(self):
            return {"id": "ctoken_auto_minted_789"}

    class DummySession:
        async def post(self, url, data=None, headers=None, timeout=None):
            posted_urls.append(url)
            if "payment_methods" in url:
                return DummyResponsePM()
            if "confirmation_tokens" in url:
                assert data["payment_method"] == "pm_auto_minted_456"
                return DummyResponseCT()
            raise ValueError(f"Unexpected url: {url}")

    card = gc.parse_card("5175465382242090|09|2030|018")
    res = await gc.create_confirmation_token(DummySession(), "pk_live_test", card)
    assert res["status"] == "OK"
    assert res["id"] == "ctoken_auto_minted_789"
    assert res["pm_id"] == "pm_auto_minted_456"
    assert posted_urls == [
        "https://api.stripe.com/v1/payment_methods",
        "https://api.stripe.com/v1/confirmation_tokens",
    ]


@pytest.mark.asyncio
async def test_create_confirmation_token_error_taxonomy():
    class DummyErrorResponse:
        status_code = 402
        def json(self):
            return {"error": {"code": "card_declined", "message": "Your card was declined."}}

    class DummySession:
        async def post(self, url, data=None, headers=None, timeout=None):
            return DummyErrorResponse()

    res = await gc.create_confirmation_token(DummySession(), "pk_live_test", "pm_declined")
    assert res["status"] in config.VERDICTS
    assert "DECLINED" in res["status"]
    assert "error" in res
