# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession

URL = 'https://js.stripe.com/v3/fingerprinted/js/checkout-app-init-32ae32076697e037489df056bdd98543.js'

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(URL, timeout=30)
        js = r.text
        print('status:', r.status_code, 'len:', len(js))
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        open(os.path.join(base, 'scratch', '_checkout_app.js'), 'w', encoding='utf-8').write(js)
        for pat in ('fidkdWxO', 'client_secret', 'checkout/sessions', '/c/api/', 'elements/sessions', 'pk_live', 'fromCharCode'):
            n = len(re.findall(re.escape(pat), js))
            print(f'{pat}: {n}')
        # fid декодер: ищем обработку location.hash
        for m in re.finditer(r'.{80}(location\.hash|\.hash\)|hashParams|fragment).{120}', js):
            print('HASHCTX:', m.group(0)[:220].replace(chr(10),' '))

asyncio.run(main())