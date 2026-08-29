# -*- coding: utf-8 :-) 
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
# mi.rK — база URL: найду объект mi с полем rK рядом с payment_pages
i = js.find('payment_pages/for_plink')
seg = js[max(0,i-3000):i+300]
# в этом сегменте ищем определение mi
m = re.search(r'mi=\{[^}]{5,400}\}', seg)
print('mi:', m.group(0)[:400] if m else 'не найден в сегменте')
# rK глобально
for mm in re.finditer(r'rK[:=]["\']([^"\']+)["\']', js):
    print('rK =', mm.group(1))