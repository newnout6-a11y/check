# -*- coding: utf-8 -*-
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid

VPN_URL = 'https://pay.1vpn.org/c/pay/cs_live_a1yIjI55ZV0YJWz6ssr7ibdd1esh2Lub7E6Zzk9iDHsnHAjZyyXSvYwKH0#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSd2cGd2ZndsdXFsamtQa2x0cGBrYHZ2QGtkZ2lgYSc%2FY2RpdmApJ2JwZGZkaGppYFNkd2xka3EnPydmamtxd2ppJyknZHVsTmB8Jz8ndW5aaWxzYFowNEpmTlxhTGBxRDJyUnxSVHxKamdBVWprPHBvZmZ3RGI0YFNxbkB8XzBrMXZjSkFsTDZ0T19pTDdXUT1maGh1NlF0NGBLdmhgdXBkbG1canM8YEppY0dgZzU1cUN2cQ%2Fx' + 'bzMnKSdjd2poVmB3c2B3Jz9xd3BgKSdnZGZuYndqcGthRmppancnPycmY2NjY2NjJyknaWR8anBxUXx1YCc%2FJ3Zsa2JpYFpscWBoJyknYGtkZ2lgVWlkZmBtamlhYHd2Jz9xd3BgeCUl'

async def probe(url, name):
    d = stripe_fid.decode_fragment(url)
    pk, cs = d.get('apiKey'), d.get('checkoutSessionId')
    print(f'--- {name}: cs={str(cs)[:30]}')
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json() if r.status_code == 200 else {}
        pi = data.get('payment_intent') or {}
        print(f'  HTTP {r.status_code} | session={data.get("status")} | PI={pi.get("status")} secret={(pi.get("client_secret") or "НЕТ")[:20]}')
        # init-проба
        r2 = await s.post(f'https://api.stripe.com/v1/payment_pages/{cs}/init',
                          data={'key': pk, 'browser_locale': 'en-US'}, headers=H, timeout=12)
        print(f'  init: {r2.status_code} {r2.text[:150]}')

async def main():
    await probe(VPN_URL, '1vpn')

asyncio.run(main())