# -*- coding: utf-8 -*-
# Сбор всех cs_live-URL из research/chat-corpus/ -> data/hit_targets.txt
import os, re, sys
from urllib.parse import unquote
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.join(ROOT, 'research', 'chat-corpus')
OUT = os.path.join(ROOT, 'data', 'hit_targets.txt')

# URL с фрагментом fid... (фрагмент критичен: без него сессию не открыть)
URL_RE = re.compile(r'https://[a-zA-Z0-9.-]+/c/pay/(cs_live_[A-Za-z0-9]+)(#[A-Za-z0-9%_.\-/=]+)')
BUY_RE = re.compile(r'(https://buy\.stripe\.com/[a-z0-9]+)')

urls, buys = set(), set()
for fn in os.listdir(CH):
    if not (fn.startswith('search_') and fn.endswith('.txt')):
        continue
    txt = open(os.path.join(CH, fn), encoding='utf-8', errors='ignore').read()
    for m in URL_RE.finditer(txt):
        frag = m.group(2) or ''
        if len(frag) > 100:  # фрагмент с fid достаточно длинный
            urls.add(m.group(0)[:600])
    for m in BUY_RE.finditer(txt):
        buys.add(m.group(1))

print(f'cs_live-URL с fid: {len(urls)}')
print(f'buy.stripe.com-линков: {len(buys)}')
with open(OUT, 'w', encoding='utf-8') as f:
    for u in sorted(urls):
        f.write(u + '\n')
print(f'-> {OUT}')
# домены
doms = sorted(set(u.split('/')[2] for u in urls))
print('домены:', doms)