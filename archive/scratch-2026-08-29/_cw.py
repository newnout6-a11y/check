# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
# определение модуля 86500 может быть без 'function' сразу после запятой
for pat in (',86500:', ' 86500:', '(86500'):
    i = js.find(pat)
    print(f'{pat!r} -> {i}')
# все вхождения cW с определением
for m in re.finditer(r'cW:function\([^)]*\)\{', js):
    i = m.start()
    print('=== cW def @', i, '===')
    print(js[i:i+700].replace(chr(10), ' '))
    print()