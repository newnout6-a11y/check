# -*- coding: utf-8 -*-
# волна 6b: 34 кандидата site:myshopify.com через прокси-ротацию (IP в 429-бане Shopify edge)
import asyncio
import json
import os
import random
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = ["https://the-original-deer-mullet-shop.myshopify.com","https://stopkillerrobots.myshopify.com","https://nwnshop.myshopify.com","https://bentonhomesteadjapan.myshopify.com","https://midsummafestival.myshopify.com","https://math-giraffe-shop.myshopify.com","https://chqsoap-2.myshopify.com","https://simplyyouscc.myshopify.com","https://midwest-fragrance-company.myshopify.com","https://voyageursoap-prd.myshopify.com","https://wholesalesuppliesplus.myshopify.com","https://naturesgardencrafts.myshopify.com","https://littleflowersoap.myshopify.com","https://naturalannie-essentials.myshopify.com","https://brooklyn-candle-studio.myshopify.com","https://thesoapfactory-727.myshopify.com","https://thepapergardengals.myshopify.com","https://savvy-places.myshopify.com","https://archer-and-olive.myshopify.com","https://daydesigner.myshopify.com","https://simply-country-ranch.myshopify.com","https://projectsprintclub.myshopify.com","https://bloomdailyplanners.myshopify.com","https://simplestories.myshopify.com","https://skigirl.myshopify.com","https://hstbmerch.myshopify.com","https://buckle-down-inc.myshopify.com","https://charlie-hustle-2.myshopify.com","https://treadlightly.myshopify.com","https://miscellany-overhaul.myshopify.com","https://the-foggy-dog.myshopify.com","https://cocopup-london.myshopify.com","https://snoopyscloset.myshopify.com","https://dogbandanaco.myshopify.com"]

PROXY_FILE = os.path.join(ROOT, '60k HTTPs _ PROXIES (2).txt')
SEM = asyncio.Semaphore(15)

def load_proxies(n=60):
    out = []
    with open(PROXY_FILE, encoding='utf-8', errors='ignore') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or not ln[0].isdigit():
                continue
            if ':' not in ln:
                continue
            out.append('http://' + ln)
            if len(out) >= n * 3:  # запас на мёртвые
                break
    return out

async def proxy_alive(p):
    try:
        async with AsyncSession(verify=False, proxy=p, timeout=6) as s:
            r = await s.get('https://www.shopify.com/robots.txt', timeout=6)
            return r.status_code in (200, 301, 302)
    except Exception:
        return False

async def check_store(store_url, proxies):
    try:
        async with SEM:
            proxy = random.choice(proxies)
            async with AsyncSession(impersonate='chrome131', verify=False, proxy=proxy) as s:
                r = await s.get(f'{store_url}/products.json?limit=100', timeout=10)
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
                                     timeout=10)
                if r_add.status_code not in (200, 201):
                    return None
                r_chk = await s.get(f'{store_url}/checkout', allow_redirects=True, timeout=12)
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
    print('[proxy] валидация...')
    raw = load_proxies(60)
    random.shuffle(raw)
    probe = raw[:120]
    res = await asyncio.gather(*[proxy_alive(p) for p in probe])
    proxies = [p for p, ok in zip(probe, res) if ok]
    print(f'[proxy] живых: {len(proxies)} из {len(probe)}')
    if len(proxies) < 5:
        print('[proxy] мало — отбой')
        return
    gates_path = os.path.join(ROOT, 'data', 'shopify_gates.json')
    existing = {}
    with open(gates_path, encoding='utf-8') as f:
        for g in json.load(f):
            existing[g['domain']] = g
    print(f"[pool] существующих: {len(existing)}; кандидатов: {len(CANDIDATES)}")
    results = await asyncio.gather(*[check_store(u, proxies) for u in CANDIDATES])
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