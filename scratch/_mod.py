# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()

# модуль 26396 — где pZ/cW
i = js.find('26396:function')
if i < 0:
    i = js.find('26396:')
print('module 26396 at:', i)
if i > 0:
    seg = js[i:i+3000]
    print(seg[:1500].replace(chr(10), ' '))