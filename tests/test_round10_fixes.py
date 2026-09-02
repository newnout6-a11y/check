# language: Python 3.12+, file: tests/test_round10_fixes.py
import os
import re
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gate_client as gc
import surface


def test_tokenize_body_includes_email_and_phone():
    card = {"number": "4111111111111111", "cvc": "123", "mm": "12", "yy": "2028"}
    telem = gc.stripe_telemetry("https://example.com", "pk_live_abc", "US",
                                email="alice.smith@gmail.com", phone="+1 555 123 4567")
    body = gc.tokenize_body(card, telem, "https://example.com")
    assert body["billing_details[email]"] == "alice.smith@gmail.com"
    assert body["billing_details[phone]"] == "+1 555 123 4567"
    assert body["billing_details[name]"] == telem["name"]
    assert body["billing_details[address][country]"] == "US"


def test_tokenize_body_handles_empty_email_and_phone():
    card = {"number": "4111111111111111", "cvc": "123", "mm": "12", "yy": "2028"}
    telem = {
        "name": "Jane Doe",
        "line1": "123 Main St",
        "city": "Dallas",
        "state": "TX",
        "postal_code": "75001",
        "country": "US",
        "guid": "guid-1",
        "muid": "muid-1",
        "sid": "sid-1",
        "payment_user_agent": "stripe.js/1",
        "time_on_page": "20000",
        "client_session_id": "cs_1",
        "elements_session_config_id": "esc_1",
        "key": "pk_live_test",
        "_stripe_version": "2020-08-27",
    }
    body = gc.tokenize_body(card, telem, "https://example.com")
    assert "billing_details[email]" not in body
    assert "billing_details[phone]" not in body


def test_stripe_telemetry_generates_email_and_phone():
    telem = gc.stripe_telemetry("https://example.com", "pk_live_abc", "US")
    assert "@" in telem["email"]
    assert len(telem["email"]) > 5
    assert "555" in telem["phone"]
    assert telem["first_name"] in telem["name"]


def test_geo_pools_spain_and_portugal_valid_codes():
    es_states = [s for _, s, _ in gc.GEO_POOLS["ES"]]
    assert "M" in es_states   # Madrid
    assert "B" in es_states   # Barcelona
    assert "V" in es_states   # Valencia
    assert "MD" not in es_states  # Non-WooCommerce code
    assert "VC" not in es_states  # Non-WooCommerce code

    pt_states = [s for _, s, _ in gc.GEO_POOLS["PT"]]
    assert "LI" in pt_states  # Lisboa
    assert "PO" in pt_states  # Porto
    assert "LIS" not in pt_states
    assert "POR" not in pt_states


def test_state_retry_regex_extracts_from_one_of_error():
    addr_err = (
        "The provided state (VC) is not valid. Must be one of: "
        "C, VI, AB, A, AL, O, AV, BA, B, CC, CS, CR, CA, CO, CU, "
        "GI, GR, GU, H, HU, J, LE, LO, LU, M, MA, ML, MU, NA, OR, "
        "O, P, GC, PO, SA, TF, S, SG, SE, SO, T, TE, TO, V, VA, BI, ZA, Z, CE, PM."
    )
    after_one_of = addr_err.split("one of:")[-1] if "one of:" in addr_err else addr_err
    short_states = re.findall(r"\b([A-Z]{1,2})\b", after_one_of)
    assert "M" in short_states
    assert "B" in short_states
    assert "V" in short_states
    assert "C" in short_states

    # Known states selector prefers matching GEO_POOLS
    known_states = [s for _, s, _ in gc.GEO_POOLS.get("ES", [])]
    match = next((st for st in short_states if st in known_states), None)
    assert match in ("M", "B", "V")


def test_surface_routes_filters_add_pm_404():
    fp_without_404 = {
        "platform": "woo_blocks",
        "payments": {"stripe_pk": "pk_live_123", "reg_nonce": True}
    }
    routes = surface._routes(fp_without_404)
    assert "setupwoo" in routes
    assert "storegate" in routes

    fp_with_404 = {
        "platform": "woo_blocks",
        "payments": {"stripe_pk": "pk_live_123", "reg_nonce": True, "add_pm_404": True}
    }
    routes_404 = surface._routes(fp_with_404)
    assert "setupwoo" not in routes_404
    assert "storegate" in routes_404
