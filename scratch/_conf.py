# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
i = js.find('payment_pages/\".concat(n,/confirm')
if i < 0:
    i = js.find('/confirm')
    # ищем рядом с payment_pages
    for m in re.finditer(r'payment_pages.{0,40}confirm', js):
        i = m.start(); break
print('confirm ctx at', i)
print(js[max(0,i-1500):i+300].replace(chr(10), ' ')[-1600:])