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
    html_altcha = '<form><altcha-widget challengeurl="/api/altcha/challenge"></altcha-widget></form>'
    det = detect_pow_type(html_altcha)
    assert det is not None
    assert det["type"] == "altcha"
    assert det["challenge_url"] == "/api/altcha/challenge"

    html_friendly = '<div class="frc-captcha" data-sitekey="FC123456"></div>'
    det_frc = detect_pow_type(html_friendly)
    assert det_frc is not None
    assert det_frc["type"] == "friendly_captcha"
    assert det_frc["sitekey"] == "FC123456"

    assert detect_pow_type("<html><body>No captcha here</body></html>") is None
    assert detect_pow_type("") is None