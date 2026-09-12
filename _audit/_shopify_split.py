
import json, pathlib, collections
sh = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
u = coll = 0
ver_under = ver_over = unver = 0
for v in sh:
    if v.get("verified"):
        if (v.get("cheapest_cents") or 0) <= 2000: ver_under += 1
        else: ver_over += 1
    else:
        unver += 1
print("verified & <=2000c:", ver_under)
print("verified & >2000c :", ver_over)
print("not verified     :", unver)
print("variants with variant_id:", sum(1 for v in sh if v.get("variant_id")))
print("keys:", sorted(sh[0].keys()))
