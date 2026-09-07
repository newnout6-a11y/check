import json
from pathlib import Path

gates_file = Path("data/shopify_gates.json")
targets_file = Path("data/shopify_targets.txt")

with open(gates_file, "r", encoding="utf-8") as f:
    gates = json.load(f)

with open(targets_file, "r", encoding="utf-8") as f:
    targets = [line.strip().replace("https://", "").replace("http://", "").rstrip("/") for line in f if line.strip()]

targets_set = set(targets)

print(f"Total gates: {len(gates)}")
print(f"Total targets: {len(targets_set)}")

in_targets = []
not_in_targets = []

for g in gates:
    d = g.get("domain") or g.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")
    if d in targets_set:
        in_targets.append(g)
    else:
        not_in_targets.append(g)

print(f"In targets: {len(in_targets)}")
print(f"Not in targets: {len(not_in_targets)}")

print("\n--- NOT IN TARGETS BREAKDOWN (34 records) ---")
for g in not_in_targets:
    cents = g.get("cheapest_cents")
    over_flag = g.get("over_cap")
    verdict = g.get("last_live_verdict")
    verified = g.get("verified")
    domain = g.get("domain") or g.get("url")
    dead_surface = g.get("dead_surface")
    needs_check = g.get("needs_live_check")
    
    print(f"Domain: {domain:35} | cents: {str(cents):6} | over_cap: {str(over_flag):5} | verified: {str(verified):5} | verdict: {str(verdict):15} | dead_sfc: {str(dead_surface):5} | needs: {str(needs_check)}")

print("\n--- ALL GATES WITH cheapest_cents > 2000 ---")
over_2000_list = []
for g in gates:
    cents = g.get("cheapest_cents", 0)
    if cents and cents > 2000:
        over_2000_list.append(g)
        domain = g.get("domain") or g.get("url")
        print(f"Domain: {domain:35} | cents: {cents:6} | over_cap: {str(g.get('over_cap')):5} | in_targets: {domain in targets_set}")

print(f"Total over 2000: {len(over_2000_list)}")
