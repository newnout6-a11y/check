# -*- coding: utf-8 -*-
# Braintree-токен через wc-ajax (плагин WC_Braintree/woo-braintree) + /cart|checkout
import asyncio, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import domains_store as ds
import gate_client as gc
from curl_cffi.requests import AsyncSession

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'braintree_targets.txt')

AJAX_TOKEN = re.compile(r'["\']?client_?[tokenTo]*["\']?\s*[:=]\s*["\']?(eyJ[A-Za-z0-9_-]{80,})', re.I) if (re := __import__('re')) else None

async def probe(sem, domain, results):
    async with sem:
        urls = [
            f'https://{domain}/?wc-ajax=wc_get_braintree_client_token',
            f'https://{domain}/wp-admin/admin-ajax.php?action=wc_get_braintree_client_token',
            f'https://{domain}/checkout/',
        ]
        for u in urls:
            try:
                async with AsyncSession(impersonate='chrome131', verify=False, timeout=10) as s:
                    r = await s.get(u, timeout=10)
                    txt = r.text or ''
                    keys = gc.extract_braintree_keys(txt)
                    if keys['client_token'] or keys['tokenization_key']:
                        results.append(domain)
                        print(f'  [BT] {domain} via {u.split("?")[0][-40:]}', flush=True)
                        return
                    # прямой eyJ-токен в ответе ajax
                    m = AJAX_TOKEN.search(txt) if AJAX_TOKEN else None
                    if m and 'authorizationFingerprint' in __import__('base64').urlsafe_b64decode(m.group(1) + '=' * (-len(m.group(1)) % 4)).decode('utf-8', 'ignore'):
                        results.append(domain)
                        print(f'  [BT] {domain} via ajax-eyJ', flush=True)
                        return
            except Exception:
                continue

async def main():
    ds.init_db()
    all_d = [r['domain'] for r in ds.all_domains()]
    print(f'сканирую {len(all_d)} доменов (braintree wc-ajax/checkout)', flush=True)
    sem = asyncio.Semaphore(25)
    results = []
    t0 = time.time()
    CH = 150
    for i in range(0, len(all_d), CH):
        chunk = all_d[i:i+CH]
        await asyncio.gather(*[probe(sem, d, results) for d in chunk])
        print(f'  [{min(i+CH, len(all_d))}/{len(all_d)}] найдено: {len(results)} ({time.time()-t0:.0f}с)', flush=True)
    if results:
        with open(OUT, 'a', encoding='utf-8') as f:
            for d in results:
                f.write(f'https://{d}\n')
    print(f'[+] ГОТОВО: {len(results)} braintree-целей', flush=True)

asyncio.run(main())