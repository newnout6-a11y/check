# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
i = js.find('86500:function')
print('86500 def at:', i)
if i > 0:
    print(js[i:i+3200].replace(chr(10), ' '))