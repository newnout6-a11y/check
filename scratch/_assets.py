# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession

CS = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz'

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(CS, timeout=20)
        html = r.text
        # полные URL inner-frame и всех js
        for m in re.findall(r'https://js\.stripe\.com/v3/[^"\'\s>]+', html):
            print('ASSET:', m[:140])

asyncio.run(main())