# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
# как строится запрос AT/de: найду функцию с fetch/XMLHttpRequest и v1
for m in re.finditer(r'.{200}("v1/"|\'v1/\'|api\.stripe\.com).{200}', js):
    t = m.group(0)
    if 'concat' in t or 'method' in t or 'POST' in t:
        print(t.replace(chr(10), ' ')[:400])
        print('---')