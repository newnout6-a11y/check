# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession

URL = "https://js.stripe.com/v3/checkout-inner-origin-frame-3e85e1d1810778953639f07eeb50c"

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(URL, timeout=20)
        print('status:', r.status_code, 'len:', len(r.text))
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        open(os.path.join(base, 'scratch', '_inner_frame.html'), 'w', encoding='utf-8').write(r.text)
        # все script src в нём
        for m in re.findall(r'src="([^"]+)"', r.text):
            print('src:', m[:120])
        # упоминания fid/fragment/api
        for pat in ('fid', 'fragment', 'api', 'checkout/sessions'):
            hits = [m.start() for m in re.finditer(pat, r.text)][:5]
            print(pat, 'hits:', hits)
            if hits:
                i = hits[0]
                print('  CTX:', r.text[max(0,i-100):i+200].replace(chr(10),' ')[:280])

asyncio.run(main())