# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
js = open("scratch/_checkout_bundle.js", encoding="utf-8").read()
for i in (8937, 11999):
    print('CTX @', i, ':', js[i-200:i+300].replace(chr(10), ' '))
    print('---')