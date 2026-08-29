# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
i = js.find('payment_pages', 880000)
print('=== ctx @', i, '===')
print(js[max(0,i-500):i+700].replace(chr(10), ' '))