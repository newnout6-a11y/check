# -*- coding: utf-8 -*-
import json, pathlib, sys, collections, sqlite3
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def lines(p):
    return [l.strip().rstrip("/") for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]
def dom(u):
    return u.replace("https://","").replace("http://","").split("/")[0].lower().removeprefix("www.")

scout = json.loads(pathlib.Path("data/scout_pool.json").read_text(encoding="utf-8"))
shop_t = {dom(x) for x in lines("data/shopify_targets.txt")}
store_t = {dom(x) for x in lines("data/store_targets.txt")}
probe = lines("data/probe_targets.txt")
scout_dom = {dom(v.get("domain","")) for v in scout}

print("=== S0-S2: полнота записей ===")
keys_present = collections.Counter()
for v in scout:
    for k, val in v.items():
        if val not in (None, "", [], {}):
            keys_present[k] += 1
print("  заполненность полей:", dict(keys_present.most_common(20)))
print("  пересечение с ротацией Shopify:", len(scout_dom & shop_t), "| с ротацией Store:", len(scout_dom & store_t))
print("  примеров с evidence:", sum(1 for v in scout if v.get("evidence")))

print()
print("=== РУЧНЫЕ ЦЕЛИ (probe_targets.txt, 17) ===")
probe_dom = {dom(x) for x in probe}
cat_shop = {dom(v.get("domain","")) for v in json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))}
cat_store = {dom(v.get("domain","")) for v in json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))}
print("  в каталоге Shopify:", len(probe_dom & cat_shop), "| в каталоге Store:", len(probe_dom & cat_store), "| в ротации:", len(probe_dom & (shop_t | store_t)))
con = sqlite3.connect("data/domains.db")
q = ",".join("?" * len(probe_dom))
rows = con.execute(f"SELECT domain, scan_result, priority FROM domains WHERE domain IN ({q})", tuple(probe_dom)).fetchall()
print("  в domains.db:", len(rows), "из", len(probe_dom))
for r_ in rows[:8]:
    print("    ", r_)
con.close()
