# -*- coding: utf-8 -*-
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid

raw = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scratch', '_vpn_url.txt'), encoding='utf-8').read().strip()
# отрезаем хвост с картой
toks = raw.split()
url = toks[1] if len(toks) > 1 and toks[1].startswith('http') else toks[0]
print('URL len:', len(url))

async def main():
    d = stripe_fid.decode_fragment(url)
    pk, cs = d.get('apiKey'), d.get('checkoutSessionId')
    print('pk:', str(pk)[:30], '| cs:', str(cs)[:30])
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        H = {'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'}
        r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}', params={'key': pk}, headers=H, timeout=12)
        data = r.json() if r.status_code == 200 else {}
        pi = data.get('payment_intent') or {}
        print(f'HTTP {r.status_code} | session={data.get("status")} | PI={pi.get("status")} amount={pi.get("amount")} secret={(pi.get("client_secret") or "НЕТ")[:20]}')
        if r.status_code != 200:
            print('body:', r.text[:300])

asyncio.run(main())