# language: Python 3.12+, file: tests/test_shopify_smart_rotation.py, target: Windows 11
# Unit tests for SmartRotator and mtime-caching in bot/gates/shopify.py
import os
import time
import pytest
from bot.gates import shopify as bg_shopify

def test_smart_rotator_no_in_flight_duplicates():
    """Concurrently picking 10 targets from 21 should never return duplicates."""
    targets = [f"https://shop{i}.com" for i in range(21)]
    # Clear state for test
    bg_shopify._in_flight.clear()
    bg_shopify._last_used.clear()
    bg_shopify._decks.clear()
    bg_shopify._quarantined_until.clear()
    
    picks = [bg_shopify._pick_target(targets, tier_key="test_tier") for _ in range(10)]
    assert len(picks) == 10
    assert len(set(picks)) == 10, f"Duplicate in-flight targets detected: {picks}"
    
    # Release all
    for p in picks:
        bg_shopify._release_target(p, success=True)
    assert len(bg_shopify._in_flight) == 0

def test_smart_rotator_cooldown_avoids_recent():
    """Targets used within COOLDOWN_SEC are deprioritized if fresh targets exist."""
    targets = [f"https://shop{i}.com" for i in range(5)]
    bg_shopify._in_flight.clear()
    bg_shopify._last_used.clear()
    bg_shopify._decks.clear()
    bg_shopify._quarantined_until.clear()
    
    t1 = bg_shopify._pick_target(targets, tier_key="cd_tier")
    bg_shopify._release_target(t1, success=True)
    
    # Next pick should NOT be t1 because 4 other targets are completely fresh
    t2 = bg_shopify._pick_target(targets, tier_key="cd_tier")
    bg_shopify._release_target(t2, success=True)
    assert t2 != t1, f"Expected fresh target, got recently used {t1}"

def test_smart_rotator_circuit_breaker():
    """Target failing twice enters quarantine and is excluded."""
    targets = ["https://fail-shop.com", "https://good-shop.com"]
    bg_shopify._in_flight.clear()
    bg_shopify._last_used.clear()
    bg_shopify._decks.clear()
    bg_shopify._quarantined_until.clear()
    bg_shopify._fails.clear()
    
    # Fail once
    t = bg_shopify._pick_target(targets, tier_key="cb_tier")
    bg_shopify._release_target(t, success=False)
    assert bg_shopify._quarantined_until.get(t, 0) <= time.monotonic()
    
    # Fail twice -> quarantine
    bg_shopify._release_target(t, success=False)
    assert bg_shopify._quarantined_until.get(t, 0) > time.monotonic()
    
    # Next pick must be good-shop
    next_pick = bg_shopify._pick_target(targets, tier_key="cb_tier")
    assert next_pick != t
    bg_shopify._release_target(next_pick, success=True)

def test_mtime_cached_loading():
    """_load_gates and _load_targets_raw use mtime cache without redundant disk reads."""
    gates1 = bg_shopify._load_gates()
    gates2 = bg_shopify._load_gates()
    assert gates1 is gates2  # Same cached Python object in memory
    
    targets1 = bg_shopify._load_targets_raw()
    targets2 = bg_shopify._load_targets_raw()
    assert targets1 == targets2
