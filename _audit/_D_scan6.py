# language: Python 3.14, file: _audit/_D_scan6.py
import pathlib, json
a = pathlib.Path("data/dork_harvested.txt").read_text(encoding="utf-8").splitlines()
b = pathlib.Path("data/harvested_domains.txt").read_text(encoding="utf-8").splitlines()
print("dork_harvested lines:", len(a), "harvested_domains lines:", len(b), "identical:", a == b)
p1 = json.loads(pathlib.Path("data/_r10_dork_probe.json").read_text(encoding="utf-8"))
p2 = json.loads(pathlib.Path("data/_r10_dork_probe2.json").read_text(encoding="utf-8"))
print("probe vs probe2: len", len(p1), len(p2), "domain sets equal:", {g["domain"] for g in p1} == {g["domain"] for g in p2})
k1 = {k for g in p1 for k in g}; k2 = {k for g in p2 for k in g}
print("keys diff:", sorted(k1 ^ k2))
imp = json.loads(pathlib.Path("data/_imp_ab.json").read_text(encoding="utf-8"))
print("_imp_ab old imps:", sorted({e.get("imp") for e in imp["old"]}), "new imps:", sorted({e.get("new") for e in imp.get("new", [])}) if isinstance(imp.get("new"), list) else type(imp.get("new")))
print("root domains.db size:", pathlib.Path("domains.db").stat().st_size, "data/domains.db:", pathlib.Path("data/domains.db").stat().st_size)
for n in ("_woo_cands.txt","_bing_cands.txt","_bing_cands2.txt","probe_targets.txt","store_targets.txt","shopify_targets.txt","hit_targets.txt","braintree_targets.txt","pi_target.txt"):
    p = pathlib.Path("data")/n
    lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    print(f"{n}: {len(lines)} записей")
js = pathlib.Path("data/upe-classic.js")
print("upe-classic.js:", js.stat().st_size, "first line:", js.read_text(encoding="utf-8", errors="ignore")[:120].replace(chr(10)," "))
