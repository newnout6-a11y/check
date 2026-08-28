# -*- coding: utf-8 -*-
# Валидация cs_live-линков: открытие сессии без confirm
import asyncio, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid
import gate_client as gc

IN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hit_targets.txt')
urls = [u.strip() for u in open(IN, encoding='utf-8') if u.strip()]
print(f'линков: {len(urls)}')

async def probe(sem, url, results):
    async with sem:
        try:
            d = stripe_fid.decode_fragment(url)
            pk, cs = d.get('apiKey'), d.get('checkoutSessionId')
            if not pk or not cs:
                results.append((url, 'BAD_FID', ''))
                return
            async with AsyncSession(impersonate='chrome131', verify=False) as s:
                r = await s.get(f'https://api.stripe.com/v1/payment_pages/{cs}',
                                params={'key': pk},
                                headers={'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'},
                                timeout=12)
                if r.status_code != 200:
                    results.append((url, f'HTTP{r.status_code}', r.text[:80]))
                    return
                data = r.json()
                pi = data.get('payment_intent') or {}
                st = pi.get('status')
                amt = f"{pi.get('amount','?')}{pi.get('currency','')}"
                if st == 'requires_payment_method':
                    results.append((url, 'LIVE', amt))
                elif pi.get('client_secret'):
                    results.append((url, f'PI:{st}', amt))
                else:
                    results.append((url, f'sess:{data.get("status")}', amt))
        except Exception as e:
            results.append((url, 'ERR', type(e).__name__))

async def main():
    sem = asyncio.Semaphore(20)
    results = []
    t0 = time.time()
    await asyncio.gather(*[probe(sem, u, results) for u in urls])
    from collections import Counter
    by = Counter(r[1] for r in results)
    print(f'проверено {len(results)} за {time.time()-t0:.0f}с')
    for k, v in by.most_common():
        print(f'  {k}: {v}')
    live = [r[0] for r in results if r[1] == 'LIVE']
    print(f'ЖИВЫХ (requires_payment_method): {len(live)}')
    for u in live[:15]:
        amt = [r[2] for r in results if r[0] == u][0]
        print(f'  {amt:10} {u[:80]}')
    with open(IN, 'w', encoding='utf-8') as f:
        for u in live:
            f.write(u + '\n')
    print('-> hit_targets.txt перезаписан живыми')

asyncio.run(main())