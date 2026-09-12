
import json, pathlib, collections
sh = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
print("last_live_verdict:", dict(collections.Counter(str(v.get("last_live_verdict")) for v in sh)))
print("verified&>2000:", sum(1 for v in sh if v.get("verified") and (v.get("cheapest_cents") or 0) > 2000))
sg = json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))
print("store verify_status:", dict(collections.Counter(str(v.get("verify_status")) for v in sg)))
print("store battle_result:", dict(collections.Counter(str(v.get("battle_result")) for v in sg)))
# tier split of the 143 in-rotation shopify targets
t = {}
for v in sh:
    if v.get("verified") and (v.get("cheapest_cents") or 0) <= 2000:
        c = v["cheapest_cents"]
        t["t1" if c <= 100 else ("t5" if c <= 500 else "t20")] = t.get("t1" if c <= 100 else ("t5" if c <= 500 else "t20"), 0) + 1
print("shopify in-rotation tiers:", t)
