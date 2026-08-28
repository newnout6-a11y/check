# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
js = open('scratch/_checkout_app.js', encoding='utf-8').read()
paths = set()
for m in re.finditer(r'\.AT\)\(\s*["\']([^"\']+)["\']\s*,\s*["\']?(GET|POST|PATCH|DELETE)', js):
    paths.add((m.group(2), m.group(1)))
for m in re.finditer(r'\.AT\)\(\s*["\']([^"\']+)["\']', js):
    paths.add(('?', m.group(1)))
for method, p in sorted(paths, key=lambda x: x[1]):
    print(f'{method:6} {p}')