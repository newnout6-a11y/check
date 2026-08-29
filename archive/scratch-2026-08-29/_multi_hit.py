# -*- coding: utf-8 -*-
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hit_gate import CsHitSession

URL = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hit_targets.txt'), encoding='utf-8').read()
URL = [u for u in URL.split() if 'a1klfHDD' in u][0]
cards = ['4937249999999991|02|31|275', '4937241006643332|02|31|275']

async def main():
    print(f'мульти-хит по {URL[:60]}...')
    for i, c in enumerate(cards, 1):
        gs = CsHitSession(URL)  # свежая сессия на каждую карту
        ok, detail = await gs.open()
        if not ok:
            print(f'  карта {i}: ЛИНК УМЕР — {detail[:70]}')
            await gs.close()
            break
        res = await gs.check_card(c)
        print(f'  карта {i} ({c[:6]}...): {res.get("status"):16} {str(res.get("detail"))[:70]}')
        await gs.close()
        await asyncio.sleep(1.2)

asyncio.run(main())