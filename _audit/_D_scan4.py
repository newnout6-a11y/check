# language: Python 3.14, file: _audit/_D_scan4.py
import sys, json, pathlib, datetime, re
sys.path.insert(0, ".")
from collections import Counter
def load(n): return json.loads((pathlib.Path("data")/n).read_text(encoding="utf-8"))
def txt(n):
    p = pathlib.Path("data")/n
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if p.exists() else []
shop, store = load("shopify_gates.json"), load("store_gates.json")
sh_j = {g["domain"]: g for g in shop if g.get("domain")}
st_j = {g["domain"]: g for g in store if g.get("domain")}
def norm(s): return s.rstrip("/").replace("https://","").replace("http://","")
sh_txt = [norm(x) for x in txt("shopify_targets.txt")]
st_txt = [norm(x) for x in txt("store_targets.txt")]
print("SHOPIFY: txt=%d json=%d" % (len(sh_txt), len(sh_j)))
print("  txt without json record (%d):" % len(set(sh_txt)-set(sh_j)), sorted(set(sh_txt)-set(sh_j))[:15])
print("  json without txt entry (%d):" % len(set(sh_j)-set(sh_txt)), sorted(set(sh_j)-set(sh_txt))[:15])
dead_sh = sorted(d for d,g in sh_j.items() if g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False)
print("  dead in json (%d):" % len(dead_sh), dead_sh)
print("  dead but still in txt:", sorted(set(dead_sh) & set(sh_txt)))
print("  verified True=%d, no verified key=%d, needs_live_check&!verified=%d, over_cap=%d" % (
    sum(1 for g in sh_j.values() if g.get("verified") is True),
    sum(1 for g in sh_j.values() if "verified" not in g),
    sum(1 for g in sh_j.values() if g.get("needs_live_check") and not g.get("verified")),
    sum(1 for g in sh_j.values() if g.get("over_cap"))))
print("  last_live_check dates:", sorted({g.get("last_live_check") for g in sh_j.values() if g.get("last_live_check")}))
print("  keys only in some records:", sorted({k for g in sh_j.values() for k in g}) )
print("STORE: txt=%d json=%d" % (len(st_txt), len(st_j)))
dead_st = sorted(d for d,g in st_j.items() if g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False)
print("  dead in json (%d):" % len(dead_st), dead_st[:20])
print("  dead but still in txt:", sorted(set(dead_st) & set(st_txt)))
print("  verified True=%d" % sum(1 for g in st_j.values() if g.get("verified") is True))
for c in (st_j, sh_j):
    ts = [g.get("updated_at") for g in c.values() if g.get("updated_at")]
    if ts: print("  updated_at:", datetime.date.fromtimestamp(min(ts)), "..", datetime.date.fromtimestamp(max(ts)))
print("SCOUT_POOL:", len(load("scout_pool.json")), "routes:", dict(Counter(r for g in load("scout_pool.json") for r in (g.get("routes") or []))))
print("  scout platforms:", dict(Counter(g.get("platform") for g in load("scout_pool.json"))))
print("  scout domains ∩ store_targets:", len({g.get("domain") for g in load("scout_pool.json")} & set(st_txt)))
imp = load("_imp_ab.json"); print("_imp_ab.json type:", type(imp).__name__, "len:", len(imp) if hasattr(imp,'__len__') else '-')
rp = load("_r10_dork_probe.json"); print("_r10_dork_probe.json:", len(rp) if hasattr(rp,'__len__') else type(rp), str(rp)[:200])
rp2 = load("_r10_dork_probe2.json"); print("_r10_dork_probe2.json:", len(rp2) if hasattr(rp2,'__len__') else type(rp2), str(rp2)[:200])
ready = load("ready_gates.json"); print("ready_gates upe_nonce:", ready[0].get("upe_nonce"), "updated_at:", datetime.date.fromtimestamp(ready[0]["updated_at"]))
fg = load("final_gates.json"); print("final_gates domains:", [g.get("domain") for g in fg], "vectors:", Counter(g.get("vector") for g in fg))
print("hit_targets raw lines:", len(txt("hit_targets.txt")), "hosts:", Counter(u.split("/")[2] if "//" in u else u.split("/")[0] for u in txt("hit_targets.txt")))
