# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open("scratch/_checkout_bundle.js", encoding="utf-8").read()
for pat in ('fidkdWxO', 'kdWxOYHwn', 'fragment', 'decodeFragment', 'getFragment', 'hashParams', 'parseFragment'):
    idxs = [m.start() for m in re.finditer(re.escape(pat), js)][:4]
    print(f'{pat}: {len([m for m in re.finditer(re.escape(pat), js)])} hits, первые: {idxs}')

# фрагмент начинается fidnandhYHdWcXxpYCc — глянем fidnand
idxs = [m.start() for m in re.finditer('fidnand', js)][:4]
print('fidnand:', idxs)
if idxs:
    i = idxs[0]
    print('CTX:', js[i-400:i+400].replace(chr(10), ' '))