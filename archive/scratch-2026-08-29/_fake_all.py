# -*- coding: utf-8 -*-
# FAKE по всем живым линкам: ищем вердикт эмитента (не amount_mismatch)
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
            continue
        res = await gs.check_card(FAKE)
        st, dt = res.get('status'), str(res.get('detail'))[:80]
        print(f'{st:18} {gs.amount}{gs.currency} {url[:55]} | {dt}')
        await gs.close()
        if st not in ('DECLINED', 'ERROR') or 'amount_mismatch' not in dt:
            print('>>> ЭМИТЕНТ ОТВЕТИЛ, стоп')
            return

asyncio.run(main())