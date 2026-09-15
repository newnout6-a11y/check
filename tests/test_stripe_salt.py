# language: Python 3.12+, file: tests/test_stripe_salt.py, target: Windows 11
"""Резолвер соли stripe.js: разбор бандла, кэш с TTL, офлайн-фолбэк, подстановка в код.

Все тесты офлайновые: сеть подменяется monkeypatch-ем, кэш пишется в tmp_path
(реальный data/stripe_salt.json не трогаем — правило гигиены репозитория).
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

import config
import stripe_salt

BUNDLE = 'var r=/*! STRIPE_JS_BUILD_SALT abc123def4*/"abc123def4d2e6131f83a19ea2f253e4289363d4";'


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SALT_CACHE_PATH", str(tmp_path / "stripe_salt.json"), raising=False)
    monkeypatch.delenv(stripe_salt.ENV_VAR, raising=False)


def test_parse_salt_extracts_marker():
    assert stripe_salt.parse_salt(BUNDLE) == "abc123def4"


def test_parse_salt_returns_none_on_changed_format():
    assert stripe_salt.parse_salt("var r='f0a6d7cfcd';") is None


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv(stripe_salt.ENV_VAR, "0123456789")
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: pytest.fail("сеть не должна вызываться"))
    assert stripe_salt.current_salt() == "0123456789"


def test_fresh_cache_used_without_network(monkeypatch):
    stripe_salt.save_cache("aaaa111122", time.time())
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: pytest.fail("сеть не должна вызываться"))
    assert stripe_salt.current_salt() == "aaaa111122"


def test_stale_cache_triggers_fetch_and_updates(monkeypatch):
    stripe_salt.save_cache("aaaa111122", time.time() - stripe_salt.cache_ttl() - 10)
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: "bbbb333344")
    assert stripe_salt.current_salt() == "bbbb333344"
    assert json.loads(pathlib.Path(config.STRIPE_SALT_CACHE_PATH).read_text(encoding="utf-8"))["salt"] == "bbbb333344"


def test_network_failure_uses_stale_cache_then_config(monkeypatch):
    stripe_salt.save_cache("cccc555566", time.time() - stripe_salt.cache_ttl() - 10)
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: None)
    assert stripe_salt.current_salt() == "cccc555566"     # просроченный кэш лучше ничего
    pathlib.Path(config.STRIPE_SALT_CACHE_PATH).unlink()
    assert stripe_salt.current_salt() == config.STRIPE_JS_BUILD


def test_broken_cache_file_is_ignored(monkeypatch):
    pathlib.Path(config.STRIPE_SALT_CACHE_PATH).write_text("{не json", encoding="utf-8")
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: None)
    assert stripe_salt.current_salt() == config.STRIPE_JS_BUILD


def test_refresh_bypasses_cache(monkeypatch):
    stripe_salt.save_cache("dddd777788", time.time())
    monkeypatch.setattr(stripe_salt, "fetch_live_salt", lambda *a, **k: "eeee999900")
    assert stripe_salt.current_salt() == "dddd777788"
    assert stripe_salt.current_salt(refresh=True) == "eeee999900"


def test_config_fallback_has_salt_format():
    assert config.STRIPE_JS_BUILD and len(config.STRIPE_JS_BUILD) == 10


def test_confirm_body_and_telemetry_use_resolver_not_constant():
    """Регрессия: соль в теле confirm и в телеметрии берётся из резолвера, а не из константы."""
    hit = pathlib.Path("hit_gate.py").read_text(encoding="utf-8")
    assert '"version": stripe_salt.current_salt()' in hit
    assert '"version": config.STRIPE_JS_BUILD' not in hit
    gc = pathlib.Path("gate_client.py").read_text(encoding="utf-8")
    assert 'stripe_salt.current_salt(), "sitekey": sitekey' in gc
    assert "stripe-js-v3/{stripe_salt.current_salt()}" in gc
