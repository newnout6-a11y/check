# language: Python, file: captcha_pow.py
"""
Proof-of-Work (PoW) Pure Python Captcha Engine.
Solves modern non-interactive/lightweight PoW captchas without external paid APIs or local ML models:
1. Altcha (SHA-256 / SHA-512)
2. Friendly Captcha v1/v2 (Blake2b-256)
3. Hashcash / Leading-zeros PoW

Zero-cost, ultra-fast CPython C-accelerated hashing (OpenSSL / hashlib).
"""

import time
import hashlib
import struct
import base64
import json
import re
from typing import Dict, Any, Optional, List


def solve_altcha(
    challenge: str,
    salt: str,
    max_number: int = 1_000_000,
    algorithm: str = "SHA-256"
) -> Optional[Dict[str, Any]]:
    """
    Solves an Altcha PoW challenge:
    Finds integer `n` in [0, max_number] such that SHA-256(salt + str(n)) == challenge.
    """
    t0 = time.perf_counter()
    salt_bytes = salt.encode("utf-8")
    challenge_lower = challenge.lower()
    algo = algorithm.upper().replace("-", "")

    if algo == "SHA512":
        hasher = hashlib.sha512
    else:
        hasher = hashlib.sha256

    for n in range(max_number + 1):
        h = hasher(salt_bytes + str(n).encode("ascii")).hexdigest()
        if h == challenge_lower:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hash_rate = int((n + 1) / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0
            return {
                "solution": n,
                "hashes_computed": n + 1,
                "elapsed_ms": round(elapsed_ms, 2),
                "hash_rate": hash_rate,
                "algorithm": algorithm
            }
    return None


def create_altcha_payload(challenge_data: Dict[str, Any], solution_number: int) -> str:
    """
    Creates the base64-encoded JSON payload expected by the target form in the 'altcha' field.
    """
    payload = {
        "algorithm": challenge_data.get("algorithm", "SHA-256"),
        "challenge": challenge_data["challenge"],
        "number": solution_number,
        "salt": challenge_data.get("salt", ""),
        "signature": challenge_data.get("signature", "")
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def solve_friendly_captcha(
    puzzle: str,
    max_iterations: int = 2_000_000
) -> Optional[Dict[str, Any]]:
    """
    Solves a Friendly Captcha PoW puzzle.
    Format: '<signature>.<base64_puzzle_buffer>' or raw base64 buffer.
    Uses BLAKE2b-256 with 128-byte padded buffer.
    """
    t0 = time.perf_counter()
    parts = puzzle.strip().split(".")
    if len(parts) == 2:
        sig, b64_buf = parts[0], parts[1]
    elif len(parts) == 1:
        sig, b64_buf = "", parts[0]
    else:
        sig, b64_buf = ".".join(parts[:-1]), parts[-1]

    rem = len(b64_buf) % 4
    if rem > 0:
        b64_buf += "=" * (4 - rem)
    try:
        raw_buf = base64.b64decode(b64_buf)
    except Exception:
        return None

    if len(raw_buf) < 20:
        return None

    num_solutions = raw_buf[18] or 1
    difficulty = raw_buf[19]
    threshold = int(2.0 ** ((255.999 - difficulty) / 8.0))

    buf = bytearray(128)
    buf[:len(raw_buf)] = raw_buf

    solutions: List[int] = []
    total_hashes = 0
    nonce = 0

    for _ in range(num_solutions):
        found = False
        while nonce < max_iterations:
            total_hashes += 1
            buf[120:128] = struct.pack("<Q", nonce)
            digest = hashlib.blake2b(buf, digest_size=32).digest()
            val = struct.unpack("<I", digest[:4])[0]
            if val < threshold:
                solutions.append(nonce)
                nonce += 1
                found = True
                break
            nonce += 1
        if not found:
            return None

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    hash_rate = int(total_hashes / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0

    sol_bytes = b"".join(struct.pack("<Q", s) for s in solutions)
    sol_b64 = base64.b64encode(sol_bytes).decode("utf-8").rstrip("=")
    response_token = f"{puzzle}.{sol_b64}"

    return {
        "solutions": solutions,
        "solution_token": response_token,
        "hashes_computed": total_hashes,
        "elapsed_ms": round(elapsed_ms, 2),
        "hash_rate": hash_rate
    }


def solve_hashcash(
    salt: str,
    required_zero_bits: int = 16,
    max_iterations: int = 2_000_000
) -> Optional[Dict[str, Any]]:
    """
    Solves generic Hashcash PoW (finding nonce where SHA-256(salt + nonce) has N leading zero bits).
    """
    t0 = time.perf_counter()
    salt_bytes = salt.encode("utf-8")
    hex_zeros = required_zero_bits // 4
    target_prefix = "0" * hex_zeros

    for n in range(max_iterations):
        h = hashlib.sha256(salt_bytes + str(n).encode("ascii")).hexdigest()
        if h.startswith(target_prefix):
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hash_rate = int((n + 1) / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0
            return {
                "nonce": n,
                "hash": h,
                "hashes_computed": n + 1,
                "elapsed_ms": round(elapsed_ms, 2),
                "hash_rate": hash_rate
            }
    return None


RE_ALTCHA = re.compile(r"<(?:altcha-widget|div)[^>]+(?:data-)?challengeurl=['\"]([^'\"]+)['\"]", re.IGNORECASE)
RE_FRIENDLY = re.compile(r"class=['\"][^'\"]*frc-captcha[^'\"]*['\"][^>]*data-sitekey=['\"]([^'\"]+)['\"]", re.IGNORECASE)


def detect_pow_type(html: str) -> Optional[Dict[str, str]]:
    """
    Inspects HTML for PoW captcha widgets (Altcha or Friendly Captcha).
    Returns dict with type and endpoint/sitekey, or None.
    """
    if not html:
        return None

    m_alt = RE_ALTCHA.search(html)
    if m_alt:
        return {"type": "altcha", "challenge_url": m_alt.group(1)}

    m_frc = RE_FRIENDLY.search(html)
    if m_frc:
        return {"type": "friendly_captcha", "sitekey": m_frc.group(1)}

    return None