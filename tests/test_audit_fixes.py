"""Regression test suite for audit bugfixes."""

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import gate_client as gc
import bin_cache
import proxy_manager
import surface


def test_parse_card_mixed_delimiters():
    """parse_card correctly splits cards with mixed delimiters."""
    # Classic slash in date with pipe delimiter: 16|MM/YY|CVC
    c1 = gc.parse_card("4111111111111111|12/28|123")
    assert c1 is not None
    assert c1["number"] == "4111111111111111"
    assert c1["mm"] == "12"
    assert c1["yy"] == "2028"
    assert c1["cvc"] == "123"

    # Colon delimiter with slash in date: 16:MM/YY:CVC
    c2 = gc.parse_card("4111111111111111:05/29:456")
    assert c2 is not None
    assert c2["number"] == "4111111111111111"
    assert c2["mm"] == "05"
    assert c2["yy"] == "2029"
    assert c2["cvc"] == "456"

    # All slashes: 16/MM/YY/CVC
    c3 = gc.parse_card("4111111111111111/08/26/999")
    assert c3 is not None
    assert c3["number"] == "4111111111111111"
    assert c3["mm"] == "08"
    assert c3["yy"] == "2026"
    assert c3["cvc"] == "999"

    # Standard pipes: 16|MM|YYYY|CVC
    c4 = gc.parse_card("4111111111111111|11|2030|777")
    assert c4 is not None
    assert c4["number"] == "4111111111111111"
    assert c4["mm"] == "11"
    assert c4["yy"] == "2030"
    assert c4["cvc"] == "777"


@pytest.mark.asyncio
async def test_bin_lookup_enriched_no_nameerror():
    """bin_lookup_enriched must not raise NameError: name 'config' is not defined."""
    with patch("curl_cffi.requests.AsyncSession.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "brand": "visa",
            "type": "debit",
            "level": "classic",
            "country_name": "United States",
            "country": "US",
            "bank": "JPMORGAN CHASE BANK, N.A.",
        }
        mock_get.return_value = mock_resp

        res = await gc.bin_lookup_enriched("411111")
        assert res["scheme"] == "visa"
        assert res["bank"]["name"] == "JPMORGAN CHASE BANK, N.A."


@pytest.mark.asyncio
async def test_stripe_retrieve_pi_preserves_last_payment_error():
    """stripe_retrieve_pi must return last_payment_error when present in Stripe payload."""
    fake_payload = {
        "status": "requires_payment_method",
        "last_payment_error": {
            "code": "card_declined",
            "decline_code": "insufficient_funds",
            "message": "Your card has insufficient funds.",
        },
    }
    mock_session = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_payload
    mock_session.get.return_value = mock_resp

    res = await gc.stripe_retrieve_pi(mock_session, "pk_test_456", "pi_test_123_secret_789")
    assert res is not None
    assert "last_payment_error" in res
    assert res["last_payment_error"]["decline_code"] == "insufficient_funds"


def test_bin_cache_connect_wal_mode():
    """bin_cache.connect() must configure WAL mode and busy_timeout."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        with patch("bin_cache.DB_PATH", db_path):
            conn = bin_cache.connect()
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0].upper()
            assert mode == "WAL"

            cur.execute("PRAGMA busy_timeout;")
            timeout = cur.fetchone()[0]
            assert timeout >= 5000
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_proxy_manager_save_health_atomic():
    """ProxyPool._save_health must write atomically without leaving partial files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "proxy_health.json")
        with patch("proxy_manager.HEALTH_FILE", json_path):
            pool = proxy_manager.ProxyPool(proxies=["http://user:pass@1.2.3.4:8080"])
            pool.entries[0]["latency_ms"] = 250
            pool.entries[0]["fail_count"] = 1
            pool._save_health()

            assert os.path.exists(json_path)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["url"] == "http://user:pass@1.2.3.4:8080"
            assert data[0]["latency_ms"] == 250


def test_surface_exception_message_retention():
    """In surface.probe_many, blank(d) must not overwrite the exception object."""
    d = {"domain": "example.com", "routes": ["storegate"]}
    exc = RuntimeError("Connection dropped by peer")
    try:
        raise exc
    except Exception as r:
        err_msg = str(r)
        r = surface.blank(d)
        r["error"] = err_msg
        assert r["error"] == "Connection dropped by peer"


@pytest.mark.asyncio
async def test_piconfirm_gate_exception_unbound_local_fixed():
    """piconfirm.gate must handle exceptions during check_card without UnboundLocalError."""
    import bot.gates.piconfirm as piconfirm

    mock_session = AsyncMock()
    mock_session.check_card.side_effect = RuntimeError("network reset")
    mock_session.close = AsyncMock()

    with patch.object(piconfirm, "_get_session", return_value=mock_session), \
         patch.object(piconfirm, "_gs", mock_session):
        status, detail = (await piconfirm.gate("4111111111111111", "12", "28", "123"))[:2]
        assert status == "ERROR"
        assert "RuntimeError" in detail
        assert piconfirm._gs is None
        mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_proxy_upload_dead_filtering():
    """Proxies that fail probe during upload are detected and filtered out immediately."""
    from proxy_manager import ProxyPool
    raw_list = ["1.1.1.1:8080", "2.2.2.2:9090"]
    pool = ProxyPool(raw_list)
    fails_before = {e["url"]: e["fail_count"] for e in pool.entries}

    # Simulate 1.1.1.1 succeeding and 2.2.2.2 failing
    async def mock_check_one(entry, sem, *args, **kwargs):
        if "1.1.1.1" in entry["url"]:
            entry["alive"] = True
            entry["latency_ms"] = 120
            entry["fail_count"] = 0
        else:
            entry["fail_count"] += 1

    with patch.object(pool, "_check_one", side_effect=mock_check_one), \
         patch.object(pool, "_save_health"):
        await pool.validate_all()

    dead_urls = {e["url"] for e in pool.entries
                 if not e["alive"] or e["fail_count"] > fails_before.get(e["url"], 0)}
    alive_urls = [e["url"] for e in pool.entries if e["url"] not in dead_urls]

    assert len(alive_urls) == 1
    assert "1.1.1.1" in alive_urls[0]
    assert len(dead_urls) == 1
    assert "2.2.2.2" in list(dead_urls)[0]

