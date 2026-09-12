# language: Python 3.14, file: _audit/_D_scan2.py
import re, pathlib, json
mn = pathlib.Path("bot/main.py").read_text(encoding="utf-8")
kb = pathlib.Path("bot/keyboards.py").read_text(encoding="utf-8")
print("=== CALLBACK HANDLER CHECK (exact literal comparisons) ===")
for cb in sorted(set(re.findall(r'callback_data="([^"]+)"', kb))):
    exact = re.search(r'data\s*==\s*"%s"' % re.escape(cb), mn) or re.search(r'data\.startswith\("%s' % re.escape(cb), mn)
    print(("OK   " if exact else "DEAD "), cb)
print("=== VERDICT INVENTORY vs config.VERDICTS ===")
import config
scope = ["setup_gate.py","store_gate.py","shopify_gate.py","hit_gate.py","confirm_gate.py"] + \
        [str(p).replace(chr(92), "/") for p in pathlib.Path("bot").rglob("*.py")]
cand = {}
for f in scope:
    p = pathlib.Path(f)
    if not p.exists(): continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r'"(?:status|verdict)"\s*:\s*"([^"]+)"', line):
            cand.setdefault(m.group(1), []).append(f"{f}:{i}")
        for m in re.finditer(r'return\s+"([A-Z][A-Z0-9_@]{2,})"', line):
            cand.setdefault(m.group(1), []).append(f"{f}:{i}")
known = set(config.VERDICTS)
for v, locs in sorted(cand.items()):
    if v not in known:
        print(f"OUT-OF-TAXONOMY {v} <- {locs[0]} (coerced to {config.coerce_verdict(v)})")
print("=== DATA CROSS-CHECK v2 ===")
def load(name):
    return json.loads((pathlib.Path("data")/name).read_text(encoding="utf-8"))
def txt_domains(name):
    p = pathlib.Path("data")/name
    if not p.exists(): return []
    return [l.strip().rstrip("/").replace("https://","").replace("http://","") for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
shop = load("shopify_gates.json"); store = load("store_gates.json")
sh_txt = txt_domains("shopify_targets.txt"); st_txt = txt_domains("store_targets.txt")
sh_j = {g["domain"]: g for g in shop if isinstance(g, dict) and g.get("domain")}
st_j = {g["domain"]: g for g in store if isinstance(g, dict) and g.get("domain")}
print("shopify: txt", len(sh_txt), "json", len(sh_j))
print("  txt without json record:", sorted(set(sh_txt)-set(sh_j))[:20], "count", len(set(sh_txt)-set(sh_j)))
print("  json dead (dead_surface/phantom/blocked/verified False):", sorted(d for d,g in sh_j.items() if g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False))
print("  json needs_live_check & not verified:", sorted(d for d,g in sh_j.items() if g.get("needs_live_check") and not g.get("verified")))
print("  verified True count:", sum(1 for g in sh_j.values() if g.get("verified") is True))
print("  no 'verified' key at all:", sum(1 for g in sh_j.values() if "verified" not in g))
print("  over_cap count:", sum(1 for g in sh_j.values() if g.get("over_cap")))
print("  txt domains also dead in json:", sorted(set(sh_txt) & {d for d,g in sh_j.items() if g.get("dead_surface") or g.get("verified") is False})[:20])
print("  last_live_check values:", sorted({g.get("last_live_check") for g in sh_j.values() if g.get("last_live_check")}))
print("store: txt", len(st_txt), "json", len(st_j))
print("  json dead:", sorted(d for d,g in st_j.items() if g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False))
print("  txt∩dead:", sorted(set(st_txt) & {d for d,g in st_j.items() if g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False}))
print("  verified True:", sum(1 for g in st_j.values() if g.get("verified") is True))
print("  updated_at range:", min(g.get("updated_at",0) for g in st_j.values()), max(g.get("updated_at",0) for g in st_j.values()))
import datetime
for nm,d in (("store_gates",st_j),("shopify_gates",sh_j)):
    ts = [g.get("updated_at") for g in d.values() if g.get("updated_at")]
    if ts:
        print(f"  {nm} updated_at min={datetime.date.fromtimestamp(min(ts))} max={datetime.date.fromtimestamp(max(ts))}")
print("=== hit_targets / dork files ===")
hit = pathlib.Path("data/hit_targets.txt").read_text(encoding="utf-8").splitlines()
print("hit_targets lines:", len([l for l in hit if l.strip() and not l.startswith('#')]))
import re as _re
print("  checkout.stripe.com count:", sum(1 for l in hit if "checkout.stripe.com" in l))
print("  buy.stripe.com count:", sum(1 for l in hit if "buy.stripe.com" in l))
print("  fid fragment count:", sum(1 for l in hit if "#fid" in l))
dh = [l.strip() for l in pathlib.Path("data/dork_harvested.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
hd = [l.strip() for l in pathlib.Path("data/harvested_domains.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
print("dork_harvested:", len(dh), "harvested_domains:", len(hd), "identical:", dh == hd)
print("scout_pool json domains in store_targets.txt:", end=" ")
sp = load("scout_pool.json")
spd = {g.get("domain") for g in sp}
print(len(set(st_txt) & spd), "of", len(st_txt))
print("scout routes histogram:", {})
from collections import Counter
c = Counter()
for g in sp:
    for r in (g.get("routes") or []):
        c[r] += 1
print("  ", dict(c))
print("scout platforms:", dict(Counter(g.get("platform") for g in sp)))
print("scout has stripe_pk:", sum(1 for g in sp if g.get("stripe_pk")), "reg_nonce:", sum(1 for g in sp if g.get("reg_nonce")))
