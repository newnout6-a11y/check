# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
for m in re.finditer(r'pZ:function', js):
    i = m.start()
    print('=== pZ @', i, '===')
    print(js[i:i+1800].replace(chr(10), ' '))
    print()