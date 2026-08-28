# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
for m in re.finditer(r'iu:function', js):
    i = m.start()
    print('=== iu @', i, '===')
    print(js[max(0,i-300):i+900].replace(chr(10), ' '))
    print()