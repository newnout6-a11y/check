# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
import os
CH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chati')
best = None
for fn in os.listdir(CH):
    if not fn.endswith('.txt'):
        continue
    for ln in open(os.path.join(CH, fn), encoding='utf-8', errors='ignore'):
        if 'pay.1vpn.org' in ln and 'cs_live' in ln:
            ln = ln.strip()
            if best is None or len(ln) > len(best):
                best = ln
print('len:', len(best) if best else 0)
if best:
    open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scratch', '_vpn_url.txt'), 'w', encoding='utf-8').write(best)
    print(best[:120])
    print('...')
    print(best[-60:])