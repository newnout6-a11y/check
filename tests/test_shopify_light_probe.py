# language: Python 3.12+, file: tests/test_shopify_light_probe.py, target: Windows 11
# Unit tests for Shopify lightweight variant probe and auto-rotation fallback.
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import shopify_gate as sg
from bot.gates import shopify as bg_shopify


def test_variant_cache_lookup_and_update():
    """Verify variant cache preloading and updates."""
    artisaire = sg.get_cached_variant("https://artisaire.myshopify.com")
    assert artisaire is not None
    assert artisaire["variant_id"] == 45178141900956
    assert artisaire["price_cents"] == 57

    sg.set_cached_variant("https://example-test-store.com", {
        "variant_id": 987654321,
        "price_cents": 150,
        "product_title": "Test Product",
    })
    cached = sg.get_cached_variant("https://example-test-store.com")
    assert cached is not None
    assert cached["variant_id"] == 987654321
    assert cached["price_cents"] == 150
    assert cached["product_title"] == "Test Product"


@pytest.mark.asyncio
async def test_probe_shopify_variant_success():
    """probe_shopify_variant returns parsed product when /cart/add.js returns 200."""
    session = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{
            "id": 12345,
            "price": 199,
            "product_title": "Sample Tea Bag",
            "variant_title": "Default",
        }]
    }
    session.post.return_value = mock_resp

    res = await sg.probe_shopify_variant(session, "https://teststore.com", 12345, max_price_cents=500)
    assert res is not None
    assert res["variant_id"] == 12345
    assert res["price_cents"] == 199
    assert res["product_title"] == "Sample Tea Bag"
    assert res["already_in_cart"] is True


@pytest.mark.asyncio
async def test_probe_shopify_variant_out_of_stock_422():
    """probe_shopify_variant returns None when /cart/add.js returns 422 Cart Error."""
    session = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {
        "status": 422,
        "message": "Cart Error",
        "description": "Cannot find variant",
    }
    session.post.return_value = mock_resp

    res = await sg.probe_shopify_variant(session, "https://teststore.com", 99999, max_price_cents=500)
    assert res is None


@pytest.mark.asyncio
async def test_probe_shopify_variant_zero_cents_skipped():
    """probe_shopify_variant rejects 0-cent items so paid card auth is guaranteed."""
    session = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{
            "id": 11111,
            "price": 0,
            "product_title": "Free Promo Sample",
        }]
    }
    session.post.return_value = mock_resp

    res = await sg.probe_shopify_variant(session, "https://teststore.com", 11111, max_price_cents=500)
    assert res is None


@pytest.mark.asyncio
async def test_probe_shopify_variant_exceeds_cap():
    """probe_shopify_variant rejects variants exceeding max_price_cents."""
    session = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{
            "id": 22222,
            "price": 1200,
            "product_title": "Expensive Item",
        }]
    }
    session.post.return_value = mock_resp

    res = await sg.probe_shopify_variant(session, "https://teststore.com", 22222, max_price_cents=500)
    assert res is None


@pytest.mark.asyncio
async def test_shopify_confirm_fast_path_skips_catalog_and_add():
    """When cached probe succeeds, shopify_confirm skips catalog fetch and redundant add to cart."""
    session = AsyncMock()

    sg.set_cached_variant("https://fast-test.com", {
        "variant_id": 55555,
        "price_cents": 85,
        "product_title": "Fast Item",
    })

    probe_resp = MagicMock()
    probe_resp.status_code = 200
    probe_resp.json.return_value = {
        "items": [{"id": 55555, "price": 85, "product_title": "Fast Item"}]
    }

    chk_resp = MagicMock()
    chk_resp.status_code = 200
    chk_resp.url = "https://fast-test.com/checkouts/cn/c1-abc123xyz"
    chk_resp.text = '<meta name="serialized-sessionToken" content="tok-session-123"/>'

    async def mock_post(url, **kwargs):
        if "cart/add.js" in url:
            return probe_resp
        if "deposit" in url:
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"id": "east-mock-vault-id"}
            return r
        if "graphql" in url:
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "data": {
                    "submitForCompletion": {
                        "__typename": "SubmitSuccess",
                        "receipt": {
                            "__typename": "ProcessedReceipt",
                            "orderStatusPageUrl": "https://fast-test.com/orders/123",
                        },
                    }
                }
            }
            return r
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {}
        return r

    session.post.side_effect = mock_post
    session.get.return_value = chk_resp

    with patch("shopify_gate.get_shopify_cheapest_product", new_callable=AsyncMock) as mock_get_cheapest:
        res = await sg.shopify_confirm(session, "https://fast-test.com", "4111111111111111|12|30|123")
        mock_get_cheapest.assert_not_called()
        assert res["status"] == "APPROVED@PAID"
        assert res["amount_cents"] == 85
        assert res["variant_id"] == 55555


@pytest.mark.asyncio
async def test_shopify_confirm_fallback_to_catalog_on_probe_failure():
    """When cached variant is out of stock (422), shopify_confirm falls back to catalog search."""
    session = AsyncMock()

    sg.set_cached_variant("https://fallback-test.com", {
        "variant_id": 99999,
        "price_cents": 50,
        "product_title": "Old Discontinued Item",
    })

    probe_fail_resp = MagicMock()
    probe_fail_resp.status_code = 422
    probe_fail_resp.json.return_value = {"status": 422, "description": "Cannot find variant"}

    add_ok_resp = MagicMock()
    add_ok_resp.status_code = 200
    add_ok_resp.json.return_value = {"items": [{"id": 77777, "price": 95}]}

    chk_resp = MagicMock()
    chk_resp.status_code = 200
    chk_resp.url = "https://fallback-test.com/checkouts/cn/c1-abc123xyz"
    chk_resp.text = '<meta name="serialized-sessionToken" content="tok-session-456"/>'

    async def mock_post(url, **kwargs):
        if "cart/add.js" in url:
            json_payload = kwargs.get("json", {}) or {}
            data_payload = kwargs.get("data", {}) or {}
            vid = json_payload.get("items", [{}])[0].get("id") or data_payload.get("id")
            if vid == 99999:
                return probe_fail_resp
            return add_ok_resp
        if "deposit" in url:
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"id": "east-mock-vault-id"}
            return r
        if "graphql" in url:
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "data": {
                    "submitForCompletion": {
                        "__typename": "SubmitFailed",
                        "reason": "insufficient_funds",
                    }
                }
            }
            return r
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {}
        return r

    session.post.side_effect = mock_post
    session.get.return_value = chk_resp

    catalog_product = {
        "product_id": 1,
        "variant_id": 77777,
        "product_title": "New Available Item",
        "price_cents": 95,
        "price_str": "0.95",
    }

    with patch("shopify_gate.get_shopify_cheapest_product", new_callable=AsyncMock) as mock_get_cheapest:
        mock_get_cheapest.return_value = catalog_product
        res = await sg.shopify_confirm(session, "https://fallback-test.com", "4111111111111111|12|30|123")
        mock_get_cheapest.assert_called_once()
        assert res["status"] == "APPROVED@CVV"
        assert res["amount_cents"] == 95
        assert res["variant_id"] == 77777

        updated = sg.get_cached_variant("https://fallback-test.com")
        assert updated["variant_id"] == 77777


@pytest.mark.asyncio
async def test_bot_gate_auto_rotates_on_out_of_stock_store():
    """bot/gates/shopify.py quarantines out-of-stock store for 24h and auto-rotates to next merchant."""
    targets = ["https://store-empty.com", "https://store-instock.com"]
    bg_shopify._in_flight.clear()
    bg_shopify._last_used.clear()
    bg_shopify._decks.clear()
    bg_shopify._quarantined_until.clear()
    bg_shopify._fails.clear()

    async def mock_check_target(target, card_raw, proxy, max_price):
        if "empty" in target:
            return {
                "status": "ERROR",
                "detail": f"No available product found under {max_price}c cap",
                "amount_cents": 0,
                "currency": "USD",
                "target": target,
            }
        return {
            "status": "DECLINED@DO_NOT_HONOR",
            "detail": "Card declined: do_not_honor",
            "amount_cents": 75,
            "currency": "USD",
            "target": target,
        }

    with patch.object(bg_shopify, "_targets", return_value=targets), \
         patch("bot.gates.shopify.check_target", side_effect=mock_check_target):

        verdict, detail, extra = await bg_shopify.gate("4111111111111111", "12", "30", "123")

        assert verdict == "DECLINED@DO_NOT_HONOR"
        assert extra["target"] == "https://store-instock.com"
        assert "[75c USD]" in detail

        quarantine_left = bg_shopify._quarantined_until.get("https://store-empty.com", 0) - time.monotonic()
        assert quarantine_left > 80000
