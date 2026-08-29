# -*- coding: utf-8 -*-
# finder4: волна DTC-брендов (свечи/кофе/одежда/еда) — добор до 50
import asyncio
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = ["https://fanjoy.com","https://fanjoy.myshopify.com","https://madeincookware.com","https://madein.myshopify.com","https://theelderstatesman.com","https://otherland.co","https://homesick.com","https://snif.co","https://pfcandleco.com","https://stumptowncoffee.com","https://intelligentsia.com","https://counterculturecoffee.com","https://onyxcoffeelab.com","https://kotn.com","https://everlane.com","https://quince.com","https://bearbottomclothing.com","https://cutsclothing.com","https://girlfriend.com","https://outerknown.com","https://cariuma.com","https://rothys.com","https://vivaia.com","https://tower28beauty.com","https://versedskin.com","https://meetblume.com","https://chomps.com","https://lakanto.com","https://jacksonschips.com","https://bushwickkitchen.com","https://bark.co","https://wildone.com","https://oliveandjune.com","https://thenorthspokane.com","https://dearkates.com","https://unboundmerino.com","https://lukafabiani.com","https://thefarmersdog.com","https://americastestkitchen.com","https://grammynoise.com","https://flosstube.com","https://hero-cosmetics.com","https://heroesjournal.co","https://notionpress.com","https://bando.com","https://shopcatalog.com","https://touchyfeely.co"]
SEM = asyncio.Semaphore(20)

async def check_store(store_url):
    try:
        async with SEM:
            async with AsyncSession(impersonate='chrome131', verify=False) as s:
                r = await s.get(f'{store_url}/products.json?limit=100', timeout=8)
                if r.status_code != 200:
                    return None
                data = r.json()
                if not isinstance(data, dict):
                    return None
                products = data.get('products', [])
                if not products:
                    return None
                cheapest = None
                min_price = 9999999
                for p in products:
                    for v in p.get('variants', []):
                        if v.get('available'):
                            try:
                                pc = int(round(float(v.get('price', '9999')) * 100))
                                if 0 < pc < min_price:
                                    min_price = pc
                                    cheapest = {'variant_id': v.get('id'),
                                                'product_title': p.get('title'),
                                                'price_cents': pc}
                            except Exception:
                                pass
                if not cheapest:
                    return None
                r_add = await s.post(f'{store_url}/cart/add.js',
                                     json={'items': [{'id': cheapest['variant_id'], 'quantity': 1}]},
                                     timeout=8)
                if r_add.status_code not in (200, 201):
                    return None
                r_chk = await s.get(f'{store_url}/checkout', allow_redirects=True, timeout=10)
                if r_chk.status_code not in (200, 302):
                    return None
                if any(mark in r_chk.text for mark in ['challenge-platform', 'cf-turnstile-wrapper', 'Just a moment...', 'Attention Required!']):
                    return None
                domain = store_url.replace('https://', '').rstrip('/')
                return {'url': store_url, 'domain': domain,
                        'cheapest_cents': cheapest['price_cents'],
                        'cheapest_title': cheapest['product_title'],
                        'variant_id': cheapest['variant_id'],
                        'currency': 'USD'}
    except Exception:
        return None

async def main():
    gates_path = os.path.join(ROOT, 'data', 'shopify_gates.json')
    existing = {}
    if os.path.exists(gates_path):
        with open(gates_path, encoding='utf-8') as f:
            for g in json.load(f):
                existing[g['domain']] = g
    print(f"[pool] существующих: {len(existing)}; кандидатов волны: {len(CANDIDATES)}")
    results = await asyncio.gather(*[check_store(u) for u in CANDIDATES])
    fresh = [r for r in results if r is not None and r['domain'] not in existing]
    print(f"[pool] живых новых: {len(fresh)}")
    for v in sorted(fresh, key=lambda x: x['cheapest_cents']):
        print(f"  + {v['domain']:42} {v['cheapest_cents']:6}c | {str(v['cheapest_title'])[:48]}")
    for v in fresh:
        existing[v['domain']] = v
    pool = sorted(existing.values(), key=lambda g: g.get('cheapest_cents', 0))
    with open(gates_path, 'w', encoding='utf-8') as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)
    targets_path = os.path.join(ROOT, 'data', 'shopify_targets.txt')
    with open(targets_path, 'w', encoding='utf-8') as f:
        for g in pool:
            f.write(g['url'] + '\n')
    print(f"[pool] итог: {len(pool)} -> shopify_gates.json + shopify_targets.txt")

if __name__ == '__main__':
    asyncio.run(main())