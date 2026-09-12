# language: Python, file: captcha_pow.py
"""
Proof-of-Work (PoW) Pure Python Captcha Engine.

Что покрыто на сентябрь 2026 (после разбора аудита, раздел 3):
1. Altcha — ДВА поколения:
   * v3 (Widget v3, апрель 2026) — memory/CPU-bound KDF: DerivedKey = KDF(algorithm, salt,
     cost, password), password = nonce + counter; сервер проверяет одним прогоном KDF
     (по документации ALTCHA). Реализован здесь как solve_altcha_kdf()/solve_altcha_any().
   * legacy — SHA-256/512(salt + str(n)) == challenge; оставлен для старых виджетов.
2. Friendly Captcha v1 (Blake2b-256, локальный puzzle). v2 (iframe <host>.frcapi.com)
   локально НЕ решается — detect_pow_type это честно сообщает, а не молчит.
3. Hashcash / Leading-zeros PoW.

Честная оговорка: KDF-путь в CPython считается на порядки медленнее legacy-брутфорса
(каждая гипотеза — полный PBKDF2-прогон), поэтому по умолчанию поиск ограничен
max_counter и рассчитан на челленджи с малым counter. Замеры — в tests/test_captcha_pow.py.
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


# --- ALTCHA v3 (Widget v3, 2026): KDF-схема вместо равенства хеша ---
# Соответствие «algorithm -> (hashlib-имя, длина ключа в байтах)». Сервер ALTCHA проверяет
# решение одним прогоном KDF: DerivedKey = KDF(Algorithm, Salt, Cost, Password),
# пароль = nonce + counter, сверяется сам ключ или его keyPrefix.
ALTCHA_V3_ALGORITHMS: Dict[str, tuple[str, int]] = {
    "PBKDF2/SHA-1": ("sha1", 20),
    "PBKDF2/SHA-256": ("sha256", 32),
    "PBKDF2/SHA-512": ("sha512", 64),
    "SHA-256": ("sha256", 32),
    "SHA-512": ("sha512", 64),
}


def altcha_kdf_key(password: str, salt: str, cost: int, algorithm: str = "PBKDF2/SHA-256") -> bytes:
    """Один прогон KDF по параметрам челленджа ALTCHA v3."""
    hash_name, dklen = ALTCHA_V3_ALGORITHMS.get(str(algorithm).upper(), ("sha256", 32))
    iterations = max(1, int(cost or 5000))
    return hashlib.pbkdf2_hmac(hash_name, password.encode("utf-8"), salt.encode("utf-8"), iterations, dklen=dklen)


def solve_altcha_kdf(
    challenge_data: Dict[str, Any],
    max_counter: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Ищет counter для ALTCHA v3: KDF(nonce + counter) даёт challenge (или его keyPrefix).

    Принимает поле в нескольких вариантах имён (nonce/number/prefix), потому что публичного
    контракта у полей нет: API ALTCHA отдаёт объект челленджа виджету и менял имена между
    версиями. Если поле не найдено — None, и вызывающий код продолжает legacy-путём.
    """
    algorithm = str(challenge_data.get("algorithm") or "PBKDF2/SHA-256")
    salt = str(challenge_data.get("salt") or "")
    nonce = str(challenge_data.get("nonce") or "")
    cost = int(challenge_data.get("cost") or challenge_data.get("iterations") or 5000)
    expected = str(challenge_data.get("challenge") or "")
    prefix = str(challenge_data.get("keyPrefix") or challenge_data.get("key_prefix") or "")
    limit = int(max_counter or challenge_data.get("maxnumber") or challenge_data.get("maxNumber") or 20_000)
    if not salt or (not expected and not prefix):
        return None

    t0 = time.perf_counter()
    prefix_l = prefix.lower()
    expected_l = expected.lower().rstrip("=")
    for counter in range(limit + 1):
        key = altcha_kdf_key(f"{nonce}{counter}", salt, cost, algorithm)
        hex_key = key.hex()
        b64_key = base64.b64encode(key).decode("utf-8").rstrip("=")
        hit = (hex_key.startswith(prefix_l) or b64_key.startswith(prefix_l)) if prefix_l else \
            (hex_key == expected_l or b64_key == expected_l)
        if hit:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "solution": counter,
                "algorithm": algorithm,
                "cost": cost,
                "attempts": counter + 1,
                "elapsed_ms": round(elapsed_ms, 2),
                "attempt_rate": int((counter + 1) / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0,
                "mode": "kdf",
            }
    return None


def solve_altcha_any(
    challenge_data: Dict[str, Any],
    max_number: int = 1_000_000,
) -> Optional[Dict[str, Any]]:
    """Диспетчер ALTCHA: сначала v3 (KDF), затем legacy (равенство хеша).

    Так старые и новые виджеты обслуживаются одним вызовом, и никто не «решает» схему,
    которой в проде уже нет (аудит 2026-09, E-01: раньше солвер знал только снятую схему).
    """
    algo = str(challenge_data.get("algorithm") or "").upper()
    looks_v3 = bool(challenge_data.get("cost") or challenge_data.get("iterations") or
                    challenge_data.get("keyPrefix") or challenge_data.get("key_prefix") or
                    "PBKDF2" in algo or "ARGON" in algo or "SCRYPT" in algo)
    if looks_v3:
        res = solve_altcha_kdf(challenge_data)
        if res:
            return res
    legacy_challenge = challenge_data.get("challenge")
    legacy_salt = challenge_data.get("salt")
    if legacy_challenge and legacy_salt:
        return solve_altcha(legacy_challenge, legacy_salt, max_number, challenge_data.get("algorithm", "SHA-256"))
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


# Детекторы виджетов. Прежний RE_ALTCHA требовал атрибут challengeurl, который из виджета
# убрали, поэтому современные формы не детектировались вовсе (аудит 2026-09, E-11).
RE_ALTCHA = re.compile(r"<(altcha-widget|altcha\b)[^>]*>|dist/altcha(?:\.min)?\.js", re.IGNORECASE)
RE_ALTCHA_CHALLENGEURL = re.compile(r"(?:data-)?challengeurl=['\"]([^'\"]+)['\"]", re.IGNORECASE)
RE_FRIENDLY_V1 = re.compile(r"class=['\"][^'\"]*frc-captcha", re.IGNORECASE)
# v2 отдаётся SDK и работает внутри iframe <host>.frcapi.com — локально не решается
RE_FRIENDLY_V2 = re.compile(r"frcapi\.com|@friendlycaptcha/sdk|friendlycaptcha\.com/sdk", re.IGNORECASE)


def detect_pow_type(html: str) -> Optional[Dict[str, str]]:
    """Определяет PoW-виджет и честно сообщает, решается ли он локально.

    Возвращает {"type", "solvable", ...}. Friendly Captcha v2 (iframe frcapi.com) помечается
    solvable=False: локального пазла там нет, и тихий None означал бы «капчи не нашли» вместо
    «нашли, но не нашим методом» (аудит 2026-09, E-10).
    """
    if not html:
        return None

    if RE_FRIENDLY_V2.search(html):
        m_site = re.search(r"data-sitekey=['\"]([^'\"]+)['\"]", html)
        return {"type": "friendly_captcha_v2", "solvable": "false",
                "sitekey": m_site.group(1) if m_site else "",
                "note": "v2 живёт в iframe <host>.frcapi.com — локальный solver покрывает только v1"}

    if RE_ALTCHA.search(html):
        m_url = RE_ALTCHA_CHALLENGEURL.search(html)
        return {"type": "altcha", "solvable": "true",
                "challenge_url": m_url.group(1) if m_url else "",
                "note": "v3 (KDF) и legacy обслуживаются solve_altcha_any()"}

    if RE_FRIENDLY_V1.search(html):
        m_site = re.search(r"data-sitekey=['\"]([^'\"]+)['\"]", html)
        return {"type": "friendly_captcha_v1", "solvable": "true",
                "sitekey": m_site.group(1) if m_site else ""}

    return None