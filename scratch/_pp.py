# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
for pat in ('payment_pages', 'checkout/sessions', '/c/pay', 'payment_page_id', 'init'):
    hits = [m.start() for m in re.finditer(re.escape(pat), js)][:6]
    print(f'{pat}: {len(hits)} hits at {hits}')
# контекст payment_pages
i = js.find('payment_pages')
if i > 0:
    print(js[max(0,i-300):i+500].replace(chr(10), ' '))