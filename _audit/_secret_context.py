# -*- coding: utf-8 -*-
import pathlib, re, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def head(p, n=3):
    t = pathlib.Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
    return [l[:70] for l in t[:n]]

print("== proxies_https_60k (first lines, masked) ==")
for l in head("data/proxies_https_60k.txt", 3):
    print("   " + re.sub(r"(?<=:)[^:@]{3,}(?=@)", "***", l)[:60])
print("== proxies.txt.example ==")
print(head("data/proxies.txt.example", 8))
print("== gate_client proxy-creds context ==")
t = pathlib.Path("gate_client.py").read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r".{0,60}[a-z0-9+.\-]+://[^\s:/@]{2,}:[^\s:/@]{2,}@[^\s/]{3,}.{0,20}", t, re.I):
    print("   " + m.group(0).strip()[:150])
print("== shopify_gates PAN-like ==")
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
    s = json.dumps(v, ensure_ascii=False)
    hits = [x.group(0) for x in PAN_RX.finditer(s) if luhn(x.group(0).replace("-",""))]
    if hits:
        print("   ", v.get("domain"), "->", [h[:6]+"..."+h[-4:] for h in hits], "| keys:", [k for k in v])
print("== scout_pool / harvested 155006...8994 context ==")
for f in ["data/scout_pool.json", "data/harvested_domains.txt"]:
    txt = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
    i = txt.find("155006")
    print("   ", f, "->", repr(txt[max(0,i-60):i+30]))
print("== bot/main.py TG defaults ==")
bm = pathlib.Path("bot/main.py").read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r"(TG_API_ID|TG_API_HASH|api_id|api_hash)[^\n]{0,80}", bm):
    print("   " + m.group(0)[:110])
