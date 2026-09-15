# -*- coding: utf-8 -*-
import json, pathlib, subprocess, sys, collections, datetime, os
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def mt(p):
    return datetime.datetime.fromtimestamp(pathlib.Path(p).stat().st_mtime).strftime("%Y-%m-%d %H:%M")

def lines(p):
    return [l.strip().rstrip("/") for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]

def dom(u):
    return u.replace("https://","").replace("http://","").split("/")[0].lower()

print("=== ФАЙЛЫ: размер и дата последней записи ===")
for f in ["data/store_targets.txt","data/shopify_targets.txt","data/store_gates.json","data/shopify_gates.json",
          "data/scout_pool.json","data/probe_targets.txt","data/ready_gates.json","data/domains.db"]:
    p = pathlib.Path(f)
    print(f"  {f:32} {p.stat().st_size:>9} б  mtime {mt(f)}")

store_cat = json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))
shop_cat  = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
st_t = lines("data/store_targets.txt"); sh_t = lines("data/shopify_targets.txt")
print()
print("=== STORE: ротация против каталога ===")
print(f"  каталог store_gates.json: {len(store_cat)} записей")
print(f"    verified=True : {sum(1 for v in store_cat if v.get('verified') is True)}")
print(f"    verify_status : {dict(collections.Counter(str(v.get('verify_status')) for v in store_cat))}")
print(f"    battle_result : {dict(collections.Counter(str(v.get('battle_result')) for v in store_cat))}")
print(f"  ротация store_targets.txt: {len(st_t)} целей")
st_set = {dom(x) for x in st_t}; cat_set = {str(v.get('domain','')).lower() for v in store_cat}
verified_set = {str(v.get('domain','')).lower() for v in store_cat if v.get('verified') is True}
print(f"    из ротации verified  : {len(st_set & verified_set)} из {len(st_set)}")
print(f"    из ротации НЕ verified: {len(st_set - verified_set)}")
print(f"    в каталоге, но не в ротации: {len(cat_set - st_set)} (это и есть остаток 59-20)")

print()
print("=== SHOPIFY: как из 177 получается 143 ===")
ver = [v for v in shop_cat if v.get('verified')]
print(f"  каталог: {len(shop_cat)} | verified: {len(ver)} | не verified: {len(shop_cat)-len(ver)}")
under = [v for v in ver if (v.get('cheapest_cents') or 0) <= 2000]
over  = [v for v in ver if (v.get('cheapest_cents') or 0) > 2000]
print(f"  verified и <= 2000c (в обойме): {len(under)}")
print(f"  verified и  > 2000c (over cap): {len(over)}")
print(f"  ротация shopify_targets.txt: {len(sh_t)}")
sh_set = {dom(x) for x in sh_t}
print(f"    совпадает с 'под капом': {len(sh_set & {str(v.get('domain','')).lower() for v in under})}")

scout = json.loads(pathlib.Path("data/scout_pool.json").read_text(encoding="utf-8"))
print()
print("=== ПРОБЫ ПОЛЕЙ (что реально лежит в записях) ===")
print("  store_gates.json ключи :", sorted(store_cat[0].keys()))
print("  shopify_gates.json ключи:", sorted(shop_cat[0].keys()))
print("  scout_pool.json ключи  :", sorted(scout[0].keys()))
print("  scout_pool пример      :", json.dumps(scout[0], ensure_ascii=False)[:300])
print("  probe_targets.txt      :", lines("data/probe_targets.txt")[:6], "...")

print()
print("=== КТО ЧИТАЕТ НАБОРЫ (grep по коду, без tests) ===")
for needle in ["scout_pool", "probe_targets", "store_targets", "shopify_targets", "domains.db"]:
    out = subprocess.run(["git","grep","-l","--","*.py"], capture_output=True, text=True).stdout.split()
    hits = []
    for f in out:
        try:
            t = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in t:
            hits.append(f)
    prod = [h for h in hits if not h.startswith("tests/") and not h.startswith("scratch/")]
    scr  = [h for h in hits if h.startswith("scratch/")]
    print(f"  {needle:16} прод: {prod}")
    print(f"  {'':16} scratch: {len(scr)} файлов")
