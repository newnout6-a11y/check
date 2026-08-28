# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
for m in re.finditer(r'.{40}26396.{80}', js):
    print(m.group(0).replace(chr(10), ' '))
    print('---')