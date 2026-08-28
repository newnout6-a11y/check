# -*- coding: utf-8 -*-
# Живая проба: что можно получить по cs_live-сессии с pk из фрагмента
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

URL = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'

async def main():
    import stripe_fid
    d = stripe_fid.decode_fragment(URL)
    pk = d['apiKey']
    cs = d['checkoutSessionId']
    secret = d['client_secret']
    print('pk:', pk[:30], '... cs:', cs[:30], '...')
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        # проба 1: retrieve session с pk
        r = await s.get(f'https://api.stripe.com/v1/checkout/sessions/{cs}',
                        params={'key': pk}, headers=H, timeout=12)
        print('GET /checkout/sessions:', r.status_code, r.text[:200])
        # проба 2: с client_secret
        r2 = await s.get(f'https://api.stripe.com/v1/checkout/sessions/{cs}',
                         params={'key': pk, 'client_secret': secret}, headers=H, timeout=12)
        print('GET +secret:', r2.status_code, r2.text[:300])

asyncio.run(main())