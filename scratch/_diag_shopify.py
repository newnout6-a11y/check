# -*- coding: utf-8 -*-
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from curl_cffi.requests import AsyncSession

STORES = ['https://stopkillerrobots.myshopify.com',
          'https://the-foggy-dog.myshopify.com',
          'https://littleflowersoap.myshopify.com',
          'https://projectsprintclub.myshopify.com']

async def diag(url):
    print(f'--- {url}')
    try:
        async with AsyncSession(impersonate='chrome131', verify=False) as s:
            r = await s.get(f'{url}/products.json?limit=10', timeout=10)
            print(f'  products.json: HTTP {r.status_code}, len={len(r.text)}')
            if r.status_code == 200:
                try:
                    d = r.json()
                    prods = d.get('products', []) if isinstance(d, dict) else []
                    print(f'  products: {len(prods)}')
                    if prods:
                        vs = prods[0].get('variants', [])
                        vid = vs[0].get('id') if vs else None
                        print(f'  first: {prods[0].get("title", "?")[:40]} vid={vid}')
                        if vid:
                            r_add = await s.post(f'{url}/cart/add.js', json={'items': [{'id': vid, 'quantity': 1}]}, timeout=10)
                            print(f'  cart/add: HTTP {r_add.status_code} {r_add.text[:80]}')
                            if r_add.status_code in (200, 201):
                                r_chk = await s.get(f'{url}/checkout', allow_redirects=True, timeout=12)
                                marks = [m for m in ['challenge-platform', 'cf-turnstile-wrapper', 'Just a moment...', 'Attention Required!'] if m in r_chk.text]
                                print(f'  checkout: HTTP {r_chk.status_code} url={str(r_chk.url)[:70]} cf={marks}')
                except Exception as e:
                    print(f'  json error: {type(e).__name__}: {e}')
    except Exception as e:
        print(f'  net error: {type(e).__name__}: {e}')

async def main():
    for u in STORES:
        await diag(u)

asyncio.run(main())