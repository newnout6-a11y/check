# -*- coding: utf-8 -*-
# Что внутри cs_live HTML-шелла: API-эндпоинты, inline-JSON, csrf
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

URL = "https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz"

async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(URL, timeout=15)
        html = r.text
        # api-эндпоинты
        apis = set(re.findall(r"https://[a-z.]*stripe[a-z.]*/[a-z0-9/_-]{3,60}", html))
        print("stripe-эндпоинты в HTML:")
        for a in sorted(apis)[:20]:
            print("  ", a)
        # inline JSON с секретами/настройками
        for pat in ("csrf", "CSRF", "session_id", "checkout_session", "locale", "merchant"):
            hits = re.findall(r".{30}" + pat + r".{60}", html)
            for h in hits[:3]:
                print(f"[{pat}] ...{h}...")
        # main.js / bundle ссылки
        js = re.findall(r'src="([^"]+.js[^"]*)"', html)
        print("JS-бандлы:", js[:8])

asyncio.run(main())
