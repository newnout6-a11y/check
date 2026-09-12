# language: Python 3.12+, file: tests/test_live_bin_metadata.py, target: Windows 11
"""Живой BIN-lookup в стиринге: данные Stripe важнее офлайн-таблиц и кэша."""
import pytest

import bin_steering
import gate_client as gc


def _card(bin_prefix: str) -> str:
    """Пробник по Луну из указанного BIN: полного PAN в исходнике нет (гигиена секретов)."""
    p = gc.gen_probe_card(bin_prefix)
    return f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"


class _Post:
    """Сессия, у которой card_metadata отвечает по префиксу."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((params or {}).get("bin_prefix"))
        prefix = (params or {}).get("bin_prefix")
        row = self.table.get(prefix)
        if not row:
            return type("R", (), {"status_code": 200, "json": lambda self=None: {"data": []}, "text": ""})()
        return type("R", (), {"status_code": 200, "json": lambda self=None: {"data": [row]}, "text": ""})()


@pytest.mark.asyncio
async def test_live_metadata_one_request_per_unique_bin():
    s = _Post({"379363": {"brand": "AMERICAN_EXPRESS", "funding": "CREDIT", "country": "US", "pan_length": 15}})
    cards = [_card("379363"), _card("379363")]
    meta = await gc.live_bin_metadata(s, "pk", cards)
    assert set(meta.keys()) == {"379363"}
    assert meta["379363"]["brand"] == "american_express"
    assert s.calls.count("379363") == 1          # один запрос на BIN, не на карту


@pytest.mark.asyncio
async def test_live_metadata_skips_unknown_bins_and_bad_cards():
    s = _Post({})
    meta = await gc.live_bin_metadata(s, "pk", [_card("999999"), "мусор"])
    assert meta == {}


@pytest.mark.asyncio
async def test_steering_prefers_live_data_over_cache():
    engine = bin_steering.BinSteeringEngine()
    live = {"ok": True, "brand": "mastercard", "funding": "debit", "country": "US", "pan_length": 16}
    p = await engine.evaluate_card(_card("517546"), quiet=True, live_meta=live)
    assert p.country_a2 == "US"
    assert "живые данные Stripe" in p.reason
    assert "funding=debit" in p.reason
    assert p.category in (bin_steering.ThreeDsCategory.DIRECT_CHECKOUT,
                          bin_steering.ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                          bin_steering.ThreeDsCategory.CHALLENGE_MANDATORY)


@pytest.mark.asyncio
async def test_steering_marks_eea_country_from_live_data():
    engine = bin_steering.BinSteeringEngine()
    live = {"ok": True, "brand": "visa", "funding": "credit", "country": "ES", "pan_length": 16}
    p = await engine.evaluate_card(_card("453927"), quiet=True, live_meta=live)
    assert p.category == bin_steering.ThreeDsCategory.CHALLENGE_MANDATORY
    assert "EEA" in p.reason
    assert "живые данные Stripe" in p.reason


@pytest.mark.asyncio
async def test_split_queue_accepts_live_meta_map():
    engine = bin_steering.BinSteeringEngine()
    live = {"379363": {"ok": True, "brand": "american_express", "funding": "credit", "country": "US", "pan_length": 15}}
    q = await engine.split_queue([_card("379363")], live_meta=live)
    total = sum(len(v) for v in q.values())
    assert total == 1
    assert q[bin_steering.ThreeDsCategory.INVALID] == []