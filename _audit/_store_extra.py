# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
def lines(p):
    return [l.strip().rstrip("/") for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
def dom(u): return u.replace("https://","").replace("http://","").split("/")[0].lower().removeprefix("www.")
cat = json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))
rot = {dom(x) for x in lines("data/store_targets.txt")}
ver = [v for v in cat if v.get("verified") is True]
print("verified всего:", len(ver))
inrot = [v for v in ver if dom(v.get("base_url") or v.get("domain","")) in rot]
notrot = [v for v in ver if dom(v.get("base_url") or v.get("domain","")) not in rot]
print("из них в ротации:", len(inrot), "| verified, но НЕ в ротации:", len(notrot))
for v in notrot:
    print(f"   {v.get('domain') or v.get('base_url')} | battle={v.get('battle_result')} | {v.get('cheapest_cents')}c {v.get('currency')} | updated {str(v.get('updated_at'))[:10]}")
print()
print("ротация (20) по battle_result:", {})
import collections
print(" ", dict(collections.Counter(str(v.get('battle_result')) for v in inrot)))
print("  cheapest_cents ротации: min", min(v.get('cheapest_cents') or 0 for v in inrot), "max", max(v.get('cheapest_cents') or 0 for v in inrot))
