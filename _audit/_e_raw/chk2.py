import sys, json, hashlib, hmac, os
sys.path.insert(0, r"C:\Users\Redmi\Downloads\pusto")
from curl_cffi.requests import AsyncSession
import asyncio

# 1. dict(session.cookies) as used by frictionless_engine.py:164
async def t():
    async with AsyncSession() as s:
        try:
            d = dict(s.cookies)
            print("dict(session.cookies) OK ->", d)
        except Exception as e:
            print("dict(session.cookies) FAIL ->", type(e).__name__, e)
        h = s.headers
        print("headers has get_list:", hasattr(h, "get_list"))
asyncio.run(t())

# 2. Altcha: current protocol per altcha 3.2.2 dist/workers/pbkdf2.js + dist/main/altcha.js
#    password = nonce||counter(uint32 BE), salt = hex, cost iterations, keyPrefix compared
import captcha_pow
cost = 1000
nonce_hex = os.urandom(16).hex()
salt_hex = os.urandom(16).hex()
salt = bytes.fromhex(salt_hex)
counter = 7
password = bytes.fromhex(nonce_hex) + counter.to_bytes(4, "big")
dk = hashlib.pbkdf2_hmac("sha256", password, salt, cost, dklen=32)
key_prefix = dk.hex()[:16]
challenge_modern = {
    "algorithm": "PBKDF2/SHA-256",
    "challenge": key_prefix,
    "salt": nonce_hex,
    "signature": "sig",
    "parameters": {"algorithm": "PBKDF2/SHA-256", "cost": cost, "keyLength": 32,
                   "nonce": nonce_hex, "salt": salt_hex, "keyPrefix": key_prefix},
}
print("modern challenge json keys:", list(challenge_modern.keys()))
res = captcha_pow.solve_altcha(challenge_modern["challenge"], challenge_modern["salt"], max_number=20000)
print("solve_altcha(modern PBKDF2/SHA-256) ->", res)
pl = captcha_pow.create_altcha_payload(challenge_modern, 7)
import base64
print("create_altcha_payload -> ", base64.b64decode(pl.encode()).decode())
print("RE_ALTCHA on modern attr:", captcha_pow.RE_ALTCHA.search('<altcha-widget challenge="https://api.example.com/challenge"></altcha-widget>'))
print("RE_ALTCHA on legacy attr:", bool(captcha_pow.RE_ALTCHA.search('<altcha-widget challengeurl="https://api.example.com/challenge"></altcha-widget>')))
