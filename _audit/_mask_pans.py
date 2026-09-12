# -*- coding: utf-8 -*-
"""Маскирует полные PAN в артефактах аудита: отчёт не должен хранить то, что мы убрали из git."""
import pathlib, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PUBLIC = {"4111111111111111","4012888888881881","4000000000000002","4242424242424242","5555555555554444",
          "5200828282828210","5105105105105100","2223003122003222","378282246310005","371449635398431",
          "378734493671000","6011111111111117","30569309025904","3530111333300000","4000000000009995"}
rx = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
def luhn(n):
    d=[int(c) for c in n]; t=0
    for i,x in enumerate(reversed(d)):
        if i%2:
            x*=2
            if x>9: x-=9
        t+=x
    return t%10==0
changed = []
for p in sorted(pathlib.Path("_audit").glob("*.md")) + sorted(pathlib.Path("_audit").glob("*.py")):
    t = p.read_text(encoding="utf-8", errors="replace")
    def sub(m):
        n = re.sub(r"[ -]", "", m.group(0))
        if 13 <= len(n) <= 19 and n not in PUBLIC and luhn(n):
            return f"{n[:6]}******{n[-4:]}"
        return m.group(0)
    nt = rx.sub(sub, t)
    if nt != t:
        p.write_text(nt, encoding="utf-8")
        changed.append(p.name)
print("masked in:", changed)
