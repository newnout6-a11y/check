# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
# найду вызов de("payment_pages/.../confirm" — что за P и w
i = js.find('"payment_pages/".concat(n,"/confirm")')
if i < 0:
    i = js.find("payment_pages/'.concat(n,'/confirm'")
print('at', i)
seg = js[max(0,i-2500):i+400]
print(seg.replace(chr(10), ' ')[-2400:])