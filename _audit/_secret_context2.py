# -*- coding: utf-8 -*-
import pathlib, re, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

t = pathlib.Path("data/proxies_https_60k.txt").read_text(encoding="utf-8", errors="replace")
pats = {
  "scheme://user:pass@host": r"[a-z0-9+.\-]+://[^\s:/@]{2,}:[^\s:/@]{2,}@[^\s/]{3,}",
  "host:port:user:pass": r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}:[^:\s]{2,}:[^:\s]{2,}\b",
  "user:pass@host:port": r"\b[^\s:@]{2,}:[^\s:@]{2,}@(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b",
  "ip:port": r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b",
}
print("== data/proxies_https_60k.txt (%d строк) ==" % len(t.splitlines()))
for name, rx in pats.items():
    print(f"   {name}: {len(re.findall(rx, t))}")
print("   пример t.me-строк:", len(re.findall(r"t\.me/", t)))

print("\n== какое поле в shopify_gates.json даёт PAN-подобное ==")
sh = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
PAN_RX = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
def luhn(n):
    d=[int(c) for c in n]; s=0
    for i,x in enumerate(reversed(d)):
        if i%2:
            x*=2
            if x>9: x-=9
        s+=x
    return s%10==0
for v in sh:
    for k, val in v.items():
        if isinstance(val, str):
            for m in PAN_RX.finditer(val):
                if luhn(m.group(0).replace("-","")):
                    print(f"   поле={k!r} значение={m.group(0)} домен={v.get('domain')}")
                    break

print("\n== контексты PAN в README / bot/main.py / formatter ==")
for f in ["README.md", "bot/main.py", "bot/utils/formatter.py"]:
    txt = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
    for m in PAN_RX.finditer(txt):
        n = m.group(0).replace("-","")
        if len(n) >= 13 and luhn(n):
            i = m.start()
            print(f"   {f}: ...{txt[max(0,i-70):i+25].replace(chr(10),' ')}...")
