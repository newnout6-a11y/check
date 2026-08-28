# language: Python 3.12+, file: tests/test_price_tiers.py, target: Windows 11
# Тесты ценовых тиров /st [1|5|20] (см. PRICE_TIERS в bot/gates/storegate.py).
from bot.gates import storegate as sg


def test_parse_tier_values():
    assert sg.parse_tier("1") == (0, 100)
    assert sg.parse_tier("5") == (100, 500)
    assert sg.parse_tier("20") == (500, 2001)
    assert sg.parse_tier("low") == (0, 100)
    assert sg.parse_tier("MID") == (100, 500)
    assert sg.parse_tier("high") == (500, 2001)
    assert sg.parse_tier(" High ") == (500, 2001)


def test_parse_tir_rejects_card():
    # PAN не должен матчиться как тир
    assert sg.parse_tier("4111111111111111") is None
    assert sg.parse_tier("4111") is None
    assert sg.parse_tier("") is None


def test_targets_no_tier_all_seven():
    targets = sg._targets()
    assert len(targets) >= 5  # живой пул; точное число зависит от data-файлов


def test_targets_tier_partition():
    """Тиры разбивают пул по цене без пересечений (данные из store_gates.json)."""
    t1 = set(sg._targets(tier=sg.parse_tier("1")))
    t5 = set(sg._targets(tier=sg.parse_tier("5")))
    t20 = set(sg._targets(tier=sg.parse_tier("20")))
    assert not (t1 & t5) and not (t5 & t20) and not (t1 & t20)
    # известные якоря боевого прогона 2026-08-27
    assert "https://thimpress.com" in t1
    assert "https://rocketgeek.com" in t5
    assert "https://essexmonastery.com" in t5
    assert "https://tricolistica.com" in t20
    assert "https://themakersclub.it" in t20


def test_cheapest_map_has_battle_prices():
    cmap = sg._cheapest_map()
    assert cmap.get("thimpress.com") == 10
    assert cmap.get("rocketgeek.com") == 100
    assert cmap.get("atriumcoffeeroasters.com") == 600  # по бою, не скану (2200)
