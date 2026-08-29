# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
for m in re.finditer(r'payment_pages["\']/?.{0,80}', js):
    print(m.group(0)[:120].replace(chr(10), ' '))
print('===')
# база запросника AT: найду fetch с api.stripe.com
for m in re.finditer(r'.{150}api\.stripe\.com.{150}', js):
    t = m.group(0)
    if 'concat' in t or 'v1' in t:
        print(t.replace(chr(10), ' ')[:300])
        print('---')