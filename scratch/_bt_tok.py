# -*- coding: utf-8 -*-
import asyncio, os, sys, base64, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get('https://wsform.com', timeout=10)
        keys = gc.extract_braintree_keys(r.text)
        ct = keys['client_token']
        pad = ct + '=' * (-len(ct) % 4)
        dec = base64.urlsafe_b64decode(pad)
        d = json.loads(dec)
        print('поля client_token:', sorted(d.keys()))
        print('fp:', str(d.get('authorizationFingerprint'))[:50])

asyncio.run(main())