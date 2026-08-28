# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open("scratch/_checkout_bundle.js", encoding="utf-8").read()
i = js.find('replace(/-/g,')
print('idx:', i)
if i > 0:
    print(js[max(0, i-700):i+500].replace(chr(10), ' '))