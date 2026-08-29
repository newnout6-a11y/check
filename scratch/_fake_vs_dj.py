# -*- coding: utf-8 -*-
# сравнение: fake (493724999...91) vs dj (4937241006643332) по живому линку
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid
import gate_client as gc
from hit_gate import CsHitSession

POOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hit_targets.txt')
urls = [u.strip() for u in open(POOL, encoding='utf-8') if u.strip()]
FAKE = '4937249999999991|02|31|275'
DJ = '4937241006643332|02|31|275'

async def main():
    for url in urls:
        gs = CsHitSession(url)
        ok, detail = await gs.open()
        if not ok:
            print(f'skip ({detail[:40]}): {url[:60]}')
            continue
        print(f'ЛИНК ЖИВ: {url[:70]}... сумма {gs.amount}{gs.currency}')
        for label, card in (('FAKE', FAKE), ('DJ  ', DJ)):
            res = await gs.check_card(card)
            print(f'  {label}: {res.get("status"):18} {str(res.get("detail"))[:90]}')
        await gs.close()
        return
    print('живых линков не осталось')

asyncio.run(main())