# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
i = js.find('window.location.hash.substring(1)')
print('hash ctx at:', i)
seg = js[i-200:i+2500]
print(seg.replace(chr(10), ' ')[:2600])