# language: Python 3.12+, file: tests/test_proxy_priority.py, target: Windows 11
# Тесты системы нормализации прокси, приоритетного выбора и отказоустойчивости.
import json
import os
import pytest
import gate_client as gc
from proxy_manager import ProxyPool


def test_normalize_proxy_pipe_formats():
    assert gc.normalize_proxy("109.199.119.160:80 | HTTP | 36ms") == "http://109.199.119.160:80"
    assert gc.normalize_proxy("124.248.191.83:1081 | SOCKS5 | 119ms") == "socks5://124.248.191.83:1081"
    assert gc.normalize_proxy("60.217.64.237:35292 | SOCKS4 | 118ms") == "socks4://60.217.64.237:35292"
    assert gc.normalize_proxy("1.2.3.4:443 | HTTPS | 50ms") == "http://1.2.3.4:443"


def test_normalize_proxy_auth_and_plain():
    assert gc.normalize_proxy("1.2.3.4:8080:user:pass") == "http://user:pass@1.2.3.4:8080"
    assert gc.normalize_proxy("1.2.3.4:8080") == "http://1.2.3.4:8080"
    assert gc.normalize_proxy("socks5://user:pass@1.1.1.1:1080") == "socks5://user:pass@1.1.1.1:1080"
    assert gc.normalize_proxy("# Comment") is None
    assert gc.normalize_proxy("") is None
    assert gc.normalize_proxy(None) is None


def test_load_proxies_file_normalization(tmp_path):
    pfile = tmp_path / "test_proxies.txt"
    pfile.write_text(
        "# Header\n"
        "109.199.119.160:80 | HTTP | 36ms\n"
        "124.248.191.83:1081 | SOCKS5 | 119ms\n"
        "109.199.119.160:80\n"  # duplicate of first
        "socks5://124.248.191.83:1081\n", # duplicate of second
        encoding="utf-8"
    )
    loaded = gc.load_proxies(str(pfile))
    assert len(loaded) == 2
    assert "http://109.199.119.160:80" in loaded
    assert "socks5://124.248.191.83:1081" in loaded


def test_proxy_pool_priority_weighting():
    pool = ProxyPool([
        "http://fast.http:80",
        "socks5://fast.socks5:1080",
        "socks4://slow.socks4:1080"
    ])
    # fast.socks5 (latency 50ms) vs fast.http (latency 50ms) vs slow (latency 1000ms)
    e_s5 = next(e for e in pool.entries if "fast.socks5" in e["url"])
    e_http = next(e for e in pool.entries if "fast.http" in e["url"])
    e_s4 = next(e for e in pool.entries if "slow.socks4" in e["url"])

    e_s5["latency_ms"] = 50
    e_http["latency_ms"] = 50
    e_s4["latency_ms"] = 1000

    w_s5 = pool._calc_weight(e_s5)
    w_http = pool._calc_weight(e_http)
    w_s4 = pool._calc_weight(e_s4)

    # SOCKS5 has 2.0x boost over HTTP at same latency
    assert w_s5 > w_http
    # Fast HTTP has huge boost over slow 1000ms SOCKS4
    assert w_http > w_s4


def test_proxy_pool_dead_proxy_excluded():
    pool = ProxyPool(["http://alive:80", "http://dead:80"])
    pool.entries[1]["fail_count"] = 3
    pool.entries[1]["alive"] = False

    # pick must NEVER pick dead proxy
    picks = {pool.pick() for _ in range(20)}
    assert "http://dead:80" not in picks
    assert "http://alive:80" in picks


def test_gc_pick_proxy_with_health_cache(tmp_path, monkeypatch):
    orig_join = os.path.join
    hfile = tmp_path / "proxy_health.json"
    hfile.write_text(json.dumps([
        {"url": "http://slow:80", "alive": True, "latency_ms": 2000, "fail_count": 0},
        {"url": "socks5://ultra_fast:1080", "alive": True, "latency_ms": 30, "fail_count": 0},
    ]), encoding="utf-8")

    monkeypatch.setattr(os.path, "join", lambda *args: str(hfile) if "proxy_health.json" in args else orig_join(*args))

    pool = ["http://slow:80", "socks5://ultra_fast:1080"]
    # Run 30 picks, fast SOCKS5 should dominate
    picks = [gc.pick_proxy(pool, None) for _ in range(30)]
    s5_count = picks.count("socks5://ultra_fast:1080")
    assert s5_count >= 25, f"Expected fast SOCKS5 to be picked majority of times, got {s5_count}/30"
