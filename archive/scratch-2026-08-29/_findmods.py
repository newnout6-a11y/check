# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

for name in ('scratch/_checkout_app.js', 'scratch/_vendor.js'):
    js = open(name, encoding='utf-8').read()
    for pat in ('pZ:function', 'cW:function', 'pZ=', 'cW=', '26396'):
        n = len(re.findall(re.escape(pat), js))
        if n:
            print(f'{name} :: {pat}: {n}')
    # iu — предобработчик хэша из 86500
    for pat in ('iu:function', '86500'):
        n = len(re.findall(re.escape(pat), js))
        if n:
            print(f'{name} :: {pat}: {n}')