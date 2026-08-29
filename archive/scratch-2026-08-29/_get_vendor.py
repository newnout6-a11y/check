# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession

URL = 'https://js.stripe.com/v3/fingerprinted/js/vendor-392b8a6c8c7ab0afb61c45efb5018914.js'

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(URL, timeout=30)
        js = r.text
        print('status:', r.status_code, 'len:', len(js))
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        open(os.path.join(base, 'scratch', '_vendor.js'), 'w', encoding='utf-8').write(js)
        i = js.find('26396:')
        print('module 26396 at:', i)
        if i > 0:
            print(js[i:i+2600].replace(chr(10), ' '))

asyncio.run(main())