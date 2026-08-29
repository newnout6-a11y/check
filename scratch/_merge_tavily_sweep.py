# -*- coding: utf-8 -*-
# мердж 26 витринных кандидатов (tavily-обход 429-бана) в пул; verified=False до live-чека
import json
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = os.path.join(ROOT, 'data', 'shopify_gates.json')
NEW = [{"domain":"the-original-deer-mullet-shop","min_price_cents":325},{"domain":"stopkillerrobots","min_price_cents":450},{"domain":"nwnshop","min_price_cents":250},{"domain":"midsummafestival","min_price_cents":200},{"domain":"math-giraffe-shop","min_price_cents":8000},{"domain":"chqsoap-2","min_price_cents":1000},{"domain":"simplyyouscc","min_price_cents":900},{"domain":"midwest-fragrance-company","min_price_cents":419},{"domain":"littleflowersoap","min_price_cents":399},{"domain":"naturalannie-essentials","min_price_cents":2000},{"domain":"brooklyn-candle-studio","min_price_cents":64800000},{"domain":"thesoapfactory-727","min_price_cents":175},{"domain":"thepapergardengals","min_price_cents":300},{"domain":"archer-and-olive","min_price_cents":500},{"domain":"daydesigner","min_price_cents":0},{"domain":"simply-country-ranch","min_price_cents":0},{"domain":"bloomdailyplanners","min_price_cents":995},{"domain":"simplestories","min_price_cents":395},{"domain":"skigirl","min_price_cents":1200},{"domain":"hstbmerch","min_price_cents":499},{"domain":"buckle-down-inc","min_price_cents":1495},{"domain":"charlie-hustle-2","min_price_cents":3800},{"domain":"treadlightly","min_price_cents":300},{"domain":"miscellany-overhaul","min_price_cents":700},{"domain":"cocopup-london","min_price_cents":300},{"domain":"dogbandanaco","min_price_cents":1699}]

with open(GATES, encoding='utf-8') as f:
    pool = json.load(f)
existing = {g['domain'] for g in pool}
added = 0
for n in NEW:
    if n['domain'] in existing:
        continue
    pool.append({
        'url': f"https://{n['domain']}.myshopify.com",
        'domain': n['domain'] + '.myshopify.com',
        'cheapest_cents': n['min_price_cents'],
        'cheapest_title': None,
        'variant_id': None,
        'currency': 'USD',
        'verified': False,
        'needs_live_check': True,
        'source': 'tavily-sweep-2026-08-29',
    })
    added += 1
pool.sort(key=lambda g: g.get('cheapest_cents') or 0)
with open(GATES, 'w', encoding='utf-8') as f:
    json.dump(pool, f, indent=2, ensure_ascii=False)
with open(os.path.join(ROOT, 'data', 'shopify_targets.txt'), 'w', encoding='utf-8') as f:
    for g in pool:
        f.write(g['url'] + '\n')
print(f'добавлено {added}; итог {len(pool)} записей')
print('verified:', sum(1 for g in pool if g.get('verified')), '| needs_live_check:', sum(1 for g in pool if g.get('needs_live_check')))