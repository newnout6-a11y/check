# -*- coding: utf-8 -*-
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid

URL = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'

async def main():
    d = stripe_fid.decode_fragment(URL)
    pk, cs = d['apiKey'], d['checkoutSessionId']
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json()
        print('status:', r.status_code)
        print('keys:', sorted(data.keys()))
        print('payment_intent:', json.dumps(data.get('payment_intent'), ensure_ascii=False)[:400] if data.get('payment_intent') else 'нет')
        # поиск client_secret и amount рекурсивно
        import re
        txt = json.dumps(data)
        for m in set(re.findall(r'((?:pi|seti)_[a-zA-Z0-9]+_secret_[a-zA-Z0-9]+)', txt)):
            print('SECRET:', m[:40] + '...')
        for k in ('amount_total', 'currency', 'payment_status', 'status', 'payment_method_types'):
            if k in data:
                print(f'{k}:', data[k])

asyncio.run(main())