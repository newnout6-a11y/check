# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()

# контексты client_secret
for m in re.finditer(r'.{100}client_secret.{150}', js):
    print('CS:', m.group(0)[:250].replace(chr(10), ' '))
    print('---')