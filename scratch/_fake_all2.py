# -*- coding: utf-8 -*-
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hit_gate import CsHitSession

POOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hit_targets.txt')
urls = [u.strip() for u in open(POOL, encoding='utf-8') if u.strip()]
FAKE = '4937249999999991|02|31|275'

async def main():
    for url in urls:
        gs = CsHitSession(url)
        ok, detail = await gs.open()
        if not ok:
            print(f'skip: {detail[:50]} | {url[:50]}')
            continue
        res = await gs.check_card(FAKE)
        st, dt = res.get('status'), str(res.get('detail'))
        real = 'amount_mismatch' not in dt and 'checkout_confirm_error' not in dt
        print(f'[{"ЭМИТЕНТ" if real else "сессия "}] {st:16} {url[:50]} | {dt[:100]}')
        await gs.close()

asyncio.run(main())