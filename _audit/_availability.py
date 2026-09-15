# -*- coding: utf-8 -*-
import json, pathlib, sys, collections
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config

def lines(p):
    return [l.strip().rstrip("/") for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]

store_t = lines("data/store_targets.txt")
shop_t = lines("data/shopify_targets.txt")
hit_t = lines("data/hit_targets.txt")
probe_t = lines("data/probe_targets.txt")

sg = json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))
sh = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
scout = json.loads(pathlib.Path("data/scout_pool.json").read_text(encoding="utf-8"))
ready = json.loads(pathlib.Path("data/ready_gates.json").read_text(encoding="utf-8"))

def cnt(seq, pred):
    return sum(1 for v in seq if pred(v))

sh_ver = cnt(sh, lambda v: v.get("verified"))
sh_under = cnt(sh, lambda v: v.get("verified") and (v.get("cheapest_cents") or 0) <= 2000)
sh_over = cnt(sh, lambda v: v.get("verified") and (v.get("cheapest_cents") or 0) > 2000)
sg_ver = cnt(sg, lambda v: v.get("verified") is True)

print("=== ПУЛЫ: сколько целей реально доступно ===")
print(f"Store API ротация   data/store_targets.txt : {len(store_t):4d} строк")
print(f"Shopify ротация     data/shopify_targets.txt: {len(shop_t):4d} строк")
print(f"ИТОГО в ротации                             : {len(store_t) + len(shop_t):4d}")
print()
print(f"Каталог Store API   data/store_gates.json  : {len(sg):4d} записей, verified {sg_ver:4d}")
print(f"Каталог Shopify     data/shopify_gates.json: {len(sh):4d} записей, verified {sh_ver:4d}")
print(f"   из них под капом $20 (в обойме)          : {sh_under:4d}")
print(f"   дороже капа (over_cap)                   : {sh_over:4d}")
print(f"   не верифицированы                        : {len(sh) - sh_ver:4d}")
print()
print(f"SetupIntent доноры  data/ready_gates.json  : {len(ready):4d}")
print(f"Конвейер S0-S2      data/scout_pool.json   : {len(scout):4d} записей")
print(f"/hit цели           data/hit_targets.txt   : {len(hit_t):4d} (все 10 мёртвы, HTTP 400)")
print(f"Ручные цели         data/probe_targets.txt : {len(probe_t):4d}")
print()
w = collections.Counter()
for v in scout:
    r = str(v.get("route") or v.get("recommended_gate") or "?")
    w[r] += 1
print("Маршруты scout_pool:", dict(w.most_common(8)))
tiers = collections.Counter()
for v in sh:
    if v.get("verified") and (v.get("cheapest_cents") or 0) <= 2000:
        c = v["cheapest_cents"]
        tiers["тир 1 (<=100c)" if c <= 100 else ("тир 5 (101-500c)" if c <= 500 else "тир 20 (501-2000c)")] += 1
print("Shopify по тирам:", dict(tiers))
print()
print(f"=== ДЛЯ ТЕКУЩЕГО ПРОГОНА: берём Store {len(store_t)} + Shopify 15 = {len(store_t) + 15} из {len(store_t) + len(shop_t)} доступных ===")
