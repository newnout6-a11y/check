# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
idxs = [m.start() for m in re.finditer('payment_pages', js)]
print('hits:', idxs)
for i in idxs:
    print('===', i, '===')
    print(js[max(0,i-200):i+260].replace(chr(10), ' '))
    print()