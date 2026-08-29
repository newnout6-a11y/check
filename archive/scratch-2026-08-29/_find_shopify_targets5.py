# -*- coding: utf-8 -*-
# finder5: ювелирка/дом/бьюти/зоо (fudge listicles + sitebuilder pets + lifesight) — добор до 50
import asyncio
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = ["https://analuisa.com","https://missoma.com","https://astridandmiyu.com","https://monicavinader.com","https://puravida.com","https://miansai.com","https://vitaly.com","https://mejuri.com","https://auratenewyork.com","https://catbirdnyc.com","https://vrai.com","https://marrowfine.com","https://pippasmall.com","https://stoneandstrand.com","https://wwake.com","https://lorenstewart.com","https://foundrae.com","https://snowehome.com","https://joybird.com","https://insideweather.com","https://luluandgeorgia.com","https://yearandday.com","https://fentybeauty.com","https://glossier.com","https://briogeohair.com","https://breadbeautysupply.com","https://megababe.com","https://necessaire.com","https://topicals.com","https://iliabeauty.com","https://alliesofskin.com","https://augustinusbader.com","https://dsanddurga.com","https://theouai.com","https://lordsandlabradors.com","https://sparkpaws.com","https://ruggable.com","https://westandwillow.com","https://lucy.co","https://blueberrypet.com","https://bigbarker.com","https://jacksongalaxy.com","https://redbarninc.com","https://petmountain.com","https://commondeer.com","https://skknbykim.com"]
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