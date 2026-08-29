# -*- coding: utf-8 -*-
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid

URL = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'

async def main():
    d = stripe_fid.decode_fragment(URL)
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(f"https://api.stripe.com/v1/payment_pages/{d['checkoutSessionId']}",
                        params={'key': d['apiKey']},
                        headers={'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'},
                        timeout=12)
        data = r.json()
        print('HTTP:', r.status_code)
        print('session status:', data.get('status'), '| payment_status:', data.get('payment_status'))
        pi = data.get('payment_intent') or {}
        print('PI status:', pi.get('status'), '| secret:', (pi.get('client_secret') or 'НЕТ')[:30])
        print('PI keys:', sorted(pi.keys())[:15])

asyncio.run(main())