"""Unit-тесты для модуля captcha_pow.py (PoW Captcha Engine)."""
import base64
import hashlib
import json
import struct
import pytest
from captcha_pow import (
    solve_altcha,
    create_altcha_payload,
    solve_friendly_captcha,
    solve_hashcash,
    detect_pow_type
)


def test_solve_altcha_success():
    salt = "test_salt_123"
    target_num = 1337
    challenge = hashlib.sha256((salt + str(target_num)).encode("ascii")).hexdigest()

    res = solve_altcha(challenge=challenge, salt=salt, max_number=10_000)
    assert res is not None
    assert res["solution"] == target_num
    assert res["hashes_computed"] == target_num + 1
    assert res["elapsed_ms"] >= 0
    assert res["hash_rate"] > 0


def test_solve_altcha_sha512():
    salt = "sha512_salt"
    target_num = 500
    challenge = hashlib.sha512((salt + str(target_num)).encode("ascii")).hexdigest()

    res = solve_altcha(challenge=challenge, salt=salt, max_number=1000, algorithm="SHA-512")
    assert res is not None
    assert res["solution"] == target_num


def test_solve_altcha_not_found():
    salt = "salt"
    challenge = "0" * 64
    res = solve_altcha(challenge=challenge, salt=salt, max_number=100)
    assert res is None


def test_create_altcha_payload():
    c_data = {
        "algorithm": "SHA-256",
        "challenge": "deadbeef",
        "salt": "testsalt",
        "signature": "sig123"
    }
    payload_b64 = create_altcha_payload(c_data, 42)
    decoded = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    assert decoded["number"] == 42
    assert decoded["challenge"] == "deadbeef"
    assert decoded["signature"] == "sig123"


def test_solve_friendly_captcha():
    # Construct a synthetic friendly-captcha puzzle buffer
    # bytes 0-17: dummy metadata, 18: n_solutions=1, 19: difficulty (e.g. 100 - very easy)
    raw = bytearray(36)
    raw[18] = 1
    raw[19] = 100  # Easy difficulty for instant unit test
    raw[28:36] = b"12345678"  # Nonce

    b64_puzzle = base64.b64encode(raw).decode("utf-8")
    puzzle_str = f"test_signature.{b64_puzzle}"

    res = solve_friendly_captcha(puzzle_str, max_iterations=50_000)
    assert res is not None
    assert len(res["solutions"]) == 1
    assert res["solution_token"].startswith(puzzle_str)
    assert res["hashes_computed"] > 0


def test_solve_hashcash():
    res = solve_hashcash("seed_test_123", required_zero_bits=12, max_iterations=100_000)
    assert res is not None
    assert res["hash"].startswith("000")
    assert res["hashes_computed"] > 0


def test_detect_pow_type():
    """Детектор знает актуальные маркеры и честно помечает нерешаемые виджеты.

    Раньше он требовал атрибут challengeurl (его из виджета убрали) и не отличал
    Friendly Captcha v2, которая локально не решается (аудит 2026-09, E-10/E-11).
    """
    html_altcha = '<form><altcha-widget challengeurl="/api/altcha/challenge"></altcha-widget></form>'
    det = detect_pow_type(html_altcha)
    assert det is not None
    assert det["type"] == "altcha"
    assert det["solvable"] == "true"
    assert det["challenge_url"] == "/api/altcha/challenge"

    # современный виджет: атрибута challengeurl уже нет — раньше такой HTML не детектился
    det_bare = detect_pow_type('<script src="/dist/altcha.min.js"></script><altcha-widget></altcha-widget>')
    assert det_bare is not None and det_bare["type"] == "altcha"
    assert det_bare["challenge_url"] == ""

    html_friendly = '<div class="frc-captcha" data-sitekey="FC123456"></div>'
    det_frc = detect_pow_type(html_friendly)
    assert det_frc is not None
    assert det_frc["type"] == "friendly_captcha_v1"
    assert det_frc["sitekey"] == "FC123456"

    # v2: iframe на frcapi.com — локально не решается, и об этом надо сказать явно
    html_v2 = '<iframe src="https://acme.frcapi.com/api/v2/captcha/iframe"></iframe>'
    det_v2 = detect_pow_type(html_v2)
    assert det_v2 is not None
    assert det_v2["type"] == "friendly_captcha_v2"
    assert det_v2["solvable"] == "false"

    assert detect_pow_type("<html><body>No captcha here</body></html>") is None
    assert detect_pow_type("") is None

def test_altcha_v3_kdf_round_trip():
    """ALTCHA v3: солвер находит counter, при котором KDF даёт заявленный ключ.

    Проверяем схему, пришедшую на смену равенству sha256(salt+n)==challenge:
    DerivedKey = KDF(algorithm, salt, cost, password), password = nonce + counter.
    """
    import captcha_pow as cp

    salt, nonce, cost, secret_counter = "salt-abc", "nonce-42", 1000, 137
    expected = cp.altcha_kdf_key(f"{nonce}{secret_counter}", salt, cost, "PBKDF2/SHA-256").hex()
    data = {"algorithm": "PBKDF2/SHA-256", "salt": salt, "nonce": nonce, "cost": cost,
            "challenge": expected, "maxnumber": 500}

    res = cp.solve_altcha_any(data)
    assert res is not None, "KDF-челлендж не решён"
    assert res["solution"] == secret_counter
    assert res["mode"] == "kdf"
    assert res["attempts"] == secret_counter + 1


def test_altcha_v3_keyprefix_mode_and_legacy_dispatch():
    """v3 умеет сверять keyPrefix, а legacy-схема остаётся рабочей через диспетчер."""
    import hashlib

    import captcha_pow as cp

    salt, nonce, cost, secret_counter = "s2", "n2", 500, 9
    key = cp.altcha_kdf_key(f"{nonce}{secret_counter}", salt, cost, "PBKDF2/SHA-256")
    data = {"algorithm": "PBKDF2/SHA-256", "salt": salt, "nonce": nonce, "cost": cost,
            "keyPrefix": key.hex()[:8], "maxnumber": 100}
    res = cp.solve_altcha_any(data)
    assert res is not None and res["solution"] == secret_counter

    # legacy: единственный n в диапазоне, для которого sha256(salt + str(n)) == challenge
    legacy_salt = "legacy-salt"
    legacy_challenge = hashlib.sha256((legacy_salt + "5").encode()).hexdigest()
    legacy = {"challenge": legacy_challenge, "salt": legacy_salt, "algorithm": "SHA-256"}
    res_legacy = cp.solve_altcha_any(legacy, max_number=50)
    assert res_legacy is not None
    assert res_legacy["solution"] == 5
    assert res_legacy.get("mode") != "kdf", "legacy-челлендж не должен уходить в KDF-путь"

