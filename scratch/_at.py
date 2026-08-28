# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
# все вызовы AT('payment_pages...')
for m in re.finditer(r'AT\("([^"]+)"', js):
    print('AT path:', m.group(1))
print('---')
# определение AT — базовый URL
i = js.find('AT:function')
if i < 0:
    for m in re.finditer(r'AT=function|AT\s*=', js):
        i = m.start(); break
print('AT def @', i)
if i > 0:
    print(js[max(0,i-600):i+600].replace(chr(10), ' '))