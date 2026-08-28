# -*- coding: utf-8 -*-
# Быстрый Braintree-скан витрин: GET / и /checkout/ -> extract_braintree_keys
# (без WP-регистрации: маркеры braintree.setup/tokenization_key часто на витрине)
import asyncio, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import domains_store as ds
import gate_client as gc
from curl_cffi.requests import AsyncSession

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'data', 'braintree_targets.txt')

async def probe(sem, domain, results):
    async with sem:
        for path in ('/', '/checkout/'):
            try:
                async with AsyncSession(impersonate='chrome131', verify=False, timeout=10) as s:
                    r = await s.get(f'https://{domain}{path}', timeout=10)
                    if r.status_code != 200:
                        continue
                    keys = gc.extract_braintree_keys(r.text)
                    if keys['has_braintree'] and (keys['client_token'] or keys['tokenization_key']):
                        results.append((domain, bool(keys['client_token']), bool(keys['tokenization_key'])))
                        print(f'  [BT] {domain} client_token={keys["client_token"] != ""} tk={keys["tokenization_key"][:20]}', flush=True)
                        return
            except Exception:
                continue

async def main():
    ds.init_db()
    due = ds.due_for_scan(hours=24)
    domains = [r['domain'] for r in due]
    print(f'[*] сканирую {len(domains)} due-доменов на braintree-маркеры', flush=True)
    sem = asyncio.Semaphore(30)
    results = []
    t0 = time.time()
    CH = 100
    for i in range(0, len(domains), CH):
        chunk = domains[i:i+CH]
        await asyncio.gather(*[probe(sem, d, results) for d in chunk])
        print(f'  [{min(i+CH, len(domains))}/{len(domains)}] найдено braintree: {len(results)} ({(time.time()-t0):.0f}с)', flush=True)
    if results:
        with open(OUT, 'a', encoding='utf-8') as f:
            for d, ct, tk in results:
                f.write(f'https://{d}\n')
    print(f'[+] ГОТОВО: {len(results)} braintree-целей -> {OUT}', flush=True)

asyncio.run(main())