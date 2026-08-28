# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
i = js.find('(86500')
print(js[i-150:i+250].replace(chr(10), ' '))
print('====')
# cW-вызовы рядом с query-строками: поищем 'betas' контекст
for m in list(re.finditer(r'cW\(', js))[:20]:
    i = m.start()
    ctx = js[max(0,i-80):i+120].replace(chr(10), ' ')
    print('CALL:', ctx[:200])
    print('---')