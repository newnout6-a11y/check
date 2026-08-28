# -*- coding: utf-8 -*-
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def main():
    target = 'https://wsform.com'
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(target, timeout=10)
        keys = gc.extract_braintree_keys(r.text)
        print('GET:', r.status_code, '| has_braintree:', keys['has_braintree'])
        print('client_token:', keys['client_token'][:40] + '...' if keys['client_token'] else 'нет')
        print('tokenization_key:', keys['tokenization_key'][:40] if keys['tokenization_key'] else 'нет')
        res = await gc.braintree_vbv_check(s, r.text, '4937241006643332|02|31|275', target)
        print('vbv result:', res)

asyncio.run(main())