# language: Python 3.12+, file: tests/test_speed_fixes.py, target: Windows 11
# Тесты скоростных фиксов (A1-A7, docs/ИССЛЕДОВАНИЕ-СКОРОСТЬ.md §4).
import asyncio
import os

import pytest

import bin_cache


# --- A1: BIN-кэш ---

@pytest.fixture()
def cache_db(tmp_path, monkeypatch):
    monkeypatch.setattr(bin_cache, "DB_PATH", str(tmp_path / "bin_cache.db"))
    bin_cache.init_db()
    return bin_cache


def test_bin_cache_roundtrip(cache_db):
    info = {"scheme": "visa", "country": {"alpha2": "US"}}
    bin_cache.put("411111", info)
    assert bin_cache.get("411111") == info


def test_bin_cache_miss_returns_none(cache_db):
    assert bin_cache.get("999999") is None


def test_bin_cache_empty_not_stored(cache_db):
    bin_cache.put("411111", {})
    assert bin_cache.get("411111") is None


def test_bin_cache_short_bin_ignored(cache_db):
    bin_cache.put("411", {"scheme": "visa"})
    assert bin_cache.get("411") is None


def test_cached_lookup_hit_no_fetch(cache_db):
    bin_cache.put("411111", {"scheme": "visa"})
    calls = []

    async def fetch(b):
        calls.append(b)
        return {"scheme": "mastercard"}

    out = asyncio.run(bin_cache.cached_lookup("411111", fetch))
    assert out == {"scheme": "visa"} and calls == []


def test_cached_lookup_miss_fetches_and_stores(cache_db):
    calls = []

    async def fetch(b):
        calls.append(b)
        return {"scheme": "mastercard", "bank": {"name": "Tinkoff"}}

    out = asyncio.run(bin_cache.cached_lookup("550000", fetch))
    assert out["scheme"] == "mastercard"
    assert bin_cache.get("550000") == out  # записан в кэш
    assert calls == ["550000"]


def test_cached_lookup_failed_fetch_not_stored(cache_db):
    async def fetch(b):
        return {}

    out = asyncio.run(bin_cache.cached_lookup("660000", fetch))
    assert out == {}
    assert bin_cache.get("660000") is None


# --- A3: выбор цели storegate ---

def test_pick_target_prefers_measured_fast():
    from bot.gates import storegate as sg
    targets = ["https://slow.example", "https://fast.example"]
    sg._health.clear()
    sg._health["https://slow.example"] = {"lat_ms": 9000, "fails": 0}
    sg._health["https://fast.example"] = {"lat_ms": 800, "fails": 0}
    picks = {sg._pick_target(targets) for _ in range(50)}
    # быстрый должен доминировать в выборке
    assert "https://fast.example" in picks
    fast_share = sum(1 for _ in range(100)
                     if sg._pick_target(targets) == "https://fast.example")
    assert fast_share > 80  # 1/800 vs 1/9000 → ~92% ожидаемо


def test_pick_target_unknown_fallback_random():
    from bot.gates import storegate as sg
    sg._health.clear()
    out = sg._pick_target(["https://a.example", "https://b.example"])
    assert out in ("https://a.example", "https://b.example")


def test_targets_filter_dead_surfaces():
    # _dead_domains сам строит путь от __file__ — достаточно вызвать
    from bot.gates import storegate as sg
    dead = sg._dead_domains()
    assert "cherryarts.org" in dead
    assert "madatshop.com" in dead
    assert "herbaura.fr" in dead


# --- A7: доступность гейтов ---

def test_available_gates_skips_dead():
    import bot.main as bm
    avail = bm._available_gates()
    # piconfirm/braintreenvbv без целей не должны попадать в авто-выбор
    assert "piconfirm" not in avail
    assert "braintreenvbv" not in avail
    assert "setupwoo" in avail
    # storegate: зависит от store_targets.txt — в репо он есть
    assert "storegate" in avail


def test_pick_gate_force_still_works():
    import bot.main as bm
    assert bm._pick_gate("setupwoo") == "setupwoo"
    assert bm._pick_gate("nope") is None


# --- A2: setupwoo/piconfirm больше не зовут сетевой bin_lookup в критическом пути ---

def test_setupwoo_gate_source_no_await_bin_lookup():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bot", "gates", "setupwoo.py"),
        encoding="utf-8").read()
    # в теле gate() не осталось блокирующего await bin_lookup (только create_task)
    gate_body = src.split("async def gate(")[1]
    assert "await bin_lookup(" not in gate_body
    assert "bin_cache.get(" in gate_body
