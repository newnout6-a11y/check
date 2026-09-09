"""
Deep audit of TG bot core functions:
1. DB operations (user, credits, premium, keys, settings).
2. Formatters (cards, BIN, translations, mass results).
3. Gate loaders and wrappers (setupwoo, storegate, shopify, piconfirm, braintreenvbv).
4. CLI gates compatibility and exports.
"""
import asyncio
import os
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config as engine_cfg
from bot import config as bot_cfg
from bot import db
from bot.utils import formatter
from bot.gates import load_gates

async def run_bot_deep_audit():
    print("=== [1] Testing DB & User Lifecycle ===")
    test_uid = 999888777
    db.ensure_user(test_uid, "test_audit_user")
    u = db.get_user(test_uid)
    print(f"User created: id={u['user_id']}, credits={u['credits']}, tier={u.get('selected_tier')}")
    assert u["user_id"] == test_uid
    
    # Add credits
    db.admin_add_credits(test_uid, 10)
    u2 = db.get_user(test_uid)
    print(f"After admin_add_credits(10): {u2['credits']} credits")
    assert u2["credits"] >= 10
    
    # Spend credit (shopify costs 2)
    ok_spend = db.spend_credit(test_uid, "shopify")
    assert ok_spend is True
    u3 = db.get_user(test_uid)
    print(f"After spend_credit('shopify'): {u3['credits']} credits")
    assert u3["credits"] == u2["credits"] - 2
    
    # Refund credit
    db.refund_credit(test_uid, "shopify")
    u4 = db.get_user(test_uid)
    print(f"After refund_credit('shopify'): {u4['credits']} credits")
    assert u4["credits"] == u2["credits"]
    
    # Key generation and redemption
    key = "TEST-KEY-AUDIT-50"
    db.add_key(key, days=0, credits=50)
    print(f"Key created: {key[:8]}...")
    res_msg = db.redeem_key(test_uid, key)
    assert "Кредиты +50" in res_msg
    print("Key redeemed: 50 credits added")
    
    # Double redeem must fail
    res_double = db.redeem_key(test_uid, key)
    assert "Неверный или уже активированный" in res_double
    print("Double redeem rejected correctly.")
    
    # Settings (gate & tier)
    db.set_user_gate(test_uid, "shopify")
    db.set_user_tier(test_uid, "5")
    settings = db.get_user_settings(test_uid)
    assert settings["selected_gate"] == "shopify"
    assert settings["selected_tier"] == "5"
    print(f"User settings verified: gate={settings['selected_gate']}, tier={settings['selected_tier']}")

    print("\n=== [2] Testing Formatter & Localization ===")
    card_info = {
        "card": "411111******1111",
        "status": "APPROVED@PAID",
        "detail": "Order placed / payment completed on Shopify",
        "latency_ms": 1420,
        "amount_cents": 100,
        "currency": "USD"
    }
    bin_info = {
        "scheme": "VISA",
        "type": "CREDIT",
        "brand": "TRADITIONAL",
        "bank": {"name": "JPMORGAN CHASE BANK, N.A."},
        "country": {"alpha2": "US", "name": "United States"}
    }
    out = formatter.format_single(
        card_raw=card_info["card"],
        binfo=bin_info,
        gate_name="Shopify Checkout ($1-5)",
        status=card_info["status"],
        detail=card_info["detail"],
        latency_ms=card_info["latency_ms"]
    )
    print("Formatted card output:\n" + out)
    assert "JPMORGAN CHASE" in out
    assert "US" in out
    assert "Shopify" in out
    
    print("\n=== [3] Testing Gate Registry ===")
    gates = load_gates()
    print(f"Loaded gates: {list(gates.keys())}")
    for expected in ["setupwoo", "storegate", "shopify", "piconfirm", "braintreenvbv"]:
        assert expected in gates, f"Missing gate: {expected}"
        meta = gates[expected]
        assert callable(meta.get("fn")), f"{expected} missing fn callable"
        assert isinstance(meta.get("cost"), int), f"{expected} missing integer cost"
    print("All 5 gate plugins satisfy required bot contract.")

    print("\n=== [4] Testing CLI Gate Sanity (dry run) ===")
    import gate_client as gc
    assert hasattr(gc, "solve_turnstile_url")
    assert hasattr(gc, "solve_pow_challenge")
    assert hasattr(gc, "detect_pow_type")
    assert hasattr(gc, "extract_turnstile_params")
    print("gate_client.py exposes zero-cost captcha solvers & turnstile extractors.")
    
    print("\n=== DEEP AUDIT PASSED 100% ===")

if __name__ == "__main__":
    asyncio.run(run_bot_deep_audit())