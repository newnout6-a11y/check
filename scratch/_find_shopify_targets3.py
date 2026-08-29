# -*- coding: utf-8 -*-
# finder3: волна 150 кандидатов (tavily-обзоры 2026 + myshopify/кастомные домены), мердж пула
import asyncio
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = ["https://kith.com","https://kith.myshopify.com","https://dedcool.com","https://pangaia.com","https://bollandbranch.com","https://drinkolipop.com","https://magicspoon.com","https://drinkag1.com","https://moonjuice.com","https://bellroy.com","https://knomo.com","https://tatcha.com","https://cuyana.com","https://schoolhouse.com","https://aimeleondore.com","https://sophiebillebrahe.com","https://functionofbeauty.com","https://nativecos.com","https://drinktrade.com","https://vuoriclothing.com","https://vuori.myshopify.com","https://manitobah.myshopify.com","https://blkbold.myshopify.com","https://vervecoffee.myshopify.com","https://tazachocolate.myshopify.com","https://packagefreeshop.myshopify.com","https://beautybakerie.myshopify.com","https://meowmeowtweet.myshopify.com","https://freshheritage.myshopify.com","https://goodee.myshopify.com","https://unitedbyblue.myshopify.com","https://hiutdenim.myshopify.com","https://uppercasemagazine.myshopify.com","https://thehoneypot.myshopify.com","https://lunchskins.myshopify.com","https://cowboy.myshopify.com","https://velasca.myshopify.com","https://bebemoss.myshopify.com","https://flybyjing.myshopify.com","https://camillebrinch.myshopify.com","https://tentree.myshopify.com","https://artisaire.myshopify.com","https://terrebleu.myshopify.com","https://pela.myshopify.com","https://yeungmancooking.myshopify.com","https://cheekbonebeauty.myshopify.com","https://troubadour.myshopify.com","https://emmabridgewater.myshopify.com","https://lootcrate.myshopify.com","https://bruvi.myshopify.com","https://cocolab.myshopify.com","https://ohsnap.com","https://anker.com","https://hyperx.com","https://koss.com","https://ghostek.com","https://nomadgoods.com","https://lorex.com","https://audeze.com","https://speckproducts.com","https://mous.co","https://taotronics.com","https://thepihut.com","https://vava.com","https://popsockets.com","https://turtlebeach.com","https://case-mate.com","https://svsound.com","https://kuoser.com","https://silidog.com","https://ofypets.com","https://ruffwear.com","https://reddress.myshopify.com","https://cupshe.com","https://taika.com","https://ghia.co","https://pixuri.com","https://dirtydogbeautyclub.com","https://bonescoffee.com","https://chamberlaincoffee.com","https://publicgoods.com","https://brandless.com","https://oliveandjune.com","https://thesill.com","https://dbrand.com","https://ridgewallet.com","https://threadwallets.com","https://cablemgmt.com","https://totalwireless.com","https://fancii.com","https://iris-usa.com","https://liquiddeath.com","https://olesmokey.com","https://litter-robot.com","https://petlibro.com","https://cuzziyo.com","https://vessi.com","https://vessi.myshopify.com","https://norda.com","https://norda.myshopify.com","https://tenlittle.com","https://coterie.com","https://millieandroo.com","https://phoxwater.com","https://wildone.com","https://fablepets.com","https://goodgoodgolf.com","https://malbon.com","https://roveconcepts.com","https://article.com","https://burrow.com","https://floydhome.com","https://amberinteriors.com","https://parachutehome.com","https://brooklinen.com","https://cozyearth.com","https://sheetsgiggles.com","https://lawlesscancelthesun.com","https://beautybio.com","https://drunkelephant.com","https://supergoop.com","https://summerfridays.com","https://glowrecipe.com","https://kravebeauty.com","https://thenormalbrand.com"]

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
                has_cf = any(mark in r_chk.text for mark in ['challenge-platform', 'cf-turnstile-wrapper', 'Just a moment...', 'Attention Required!'])
                if has_cf:
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