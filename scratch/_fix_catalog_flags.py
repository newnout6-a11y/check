import json
from pathlib import Path

p = Path("data/shopify_gates.json")
with open(p, "r", encoding="utf-8") as f:
    gates = json.load(f)

targets = set(line.strip().replace("https://", "").replace("http://", "").rstrip("/") for line in open("data/shopify_targets.txt", encoding="utf-8") if line.strip())

over_cap_count = 0
dead_count = 0
verified_under_cap = 0

for g in gates:
    d = g.get("domain") or g.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")
    cents = g.get("cheapest_cents")
    
    if cents is not None and cents > 2000:
        over_cap_count += 1
        g["over_cap"] = True
        if d in ("camillebrinch.myshopify.com", "sophiebillebrahe.com"):
            g["over_cap_note"] = f"каталог дороже $20 ({cents}c, live recheck 2026-09-06), исключён из ротации"
        elif not g.get("over_cap_note") and not g.get("note"):
            g["over_cap_note"] = f"каталог дороже $20 капа ({cents}c)"
    elif g.get("verified") is False or g.get("last_live_verdict") in ("DEAD", "ERROR", "NO_PRODUCTS"):
        dead_count += 1
        g["dead_surface"] = True
        g["verified"] = False
    elif d in targets:
        verified_under_cap += 1

with open(p, "w", encoding="utf-8") as f:
    json.dump(gates, f, indent=2, ensure_ascii=False)

print(f"Updated {p}:")
print(f"  Total gates: {len(gates)}")
print(f"  Verified under cap ($20): {verified_under_cap}")
print(f"  over_cap (True): {over_cap_count}")
print(f"  dead_surface (True) / unverified: {dead_count}")
print(f"  Sum: {verified_under_cap + over_cap_count + dead_count}")
