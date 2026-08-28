# -*- coding: utf-8 -*-
# Методные сообщения: пары сайт+гейт, команды /hit, гейт-анонсы
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
CH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chati")

pat_gate = re.compile(r"(?i)(gateway|гейт|gate)\s*[:=⇾>]?\s*([A-Za-z][\w .&#-]{2,30})")
pat_hit = re.compile(r"/hit\s+(\S+)")
seen = set()
lines_out = []
for fn in sorted(os.listdir(CH)):
    if not (fn.startswith("search_") and fn.endswith(".txt")):
        continue
    with open(os.path.join(CH, fn), encoding="utf-8", errors="ignore") as f:
        for ln in f:
            t = ln.strip()
            if len(t) < 15 or t in seen:
                continue
            hit = pat_hit.search(t)
            gate = pat_gate.search(t)
            if hit:
                seen.add(t)
                lines_out.append("HIT: " + t[:150])
            elif gate and re.search(r"(?i)stripe|shopify|braintree|adyen|square|paypal|opus|checkout|nmi|cyber", gate.group(2)):
                seen.add(t)
                lines_out.append("GATE: " + t[:150])
print(f"всего методных строк: {len(lines_out)}")
for l in lines_out[:60]:
    print(l)
