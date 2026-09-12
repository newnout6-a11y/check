# language: Python 3.14, file: _audit/_D_scan.py, target: Windows 11
# Сканер мёртвых callback'ов, фантомных ссылок на файлы и расхождений data/*.json vs data/*.txt
import re, pathlib, json
root = pathlib.Path(".")
scope = ["setup_gate.py","store_gate.py","shopify_gate.py","hit_gate.py","confirm_gate.py","funnel.py"] + \
        [str(p) for p in pathlib.Path("bot").rglob("*.py")]
print("=== CALLBACK DATA IN keyboards.py vs main.py ===")
kb_p = pathlib.Path("bot/keyboards.py")
kb = kb_p.read_text(encoding="utf-8")
mn_p = pathlib.Path("bot/main.py")
mn = mn_p.read_text(encoding="utf-8")
cbs = sorted(set(re.findall(r'callback_data="([^"]+)"', kb)))
for cb in cbs:
    handled = ('"%s"' % cb) in mn or ("'%s'" % cb) in mn or cb.split(":")[0] in mn
    print(("OK   " if handled else "DEAD "), cb)
print("=== menu:* strings used in main.py vs keyboards ===")
for m in sorted(set(re.findall(r'"(menu:[a-z_]+)"', mn))):
    print(m, "in_keyboards=", m in kb)
print("=== PHANTOM FILE REFS (string literals) ===")
pat = re.compile(r'["\']([A-Za-z0-9_./\\-]*\.(?:py|md|json|txt|js|db))["\']')
seen = set()
for f in scope:
    p = pathlib.Path(f)
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for m in pat.finditer(txt):
        ref = m.group(1)
        if ref in seen:
            continue
        seen.add(ref)
        ok = pathlib.Path(ref).exists() or (pathlib.Path("data") / pathlib.Path(ref).name).exists() \
             or (pathlib.Path("bot") / pathlib.Path(ref).name).exists()
        if not ok:
            line = txt[:m.start()].count("\n") + 1
            print(f"MISSING-REF {f}:{line} -> {ref}")
print("=== REF PATHS (docs/research/data dirs) ===")
for f in scope:
    p = pathlib.Path(f)
    if not p.exists():
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r'(?:research|docs|tests|scratch|data)[/\\][A-Za-z0-9_./\\-]+', line):
            ref = m.group(0).replace(chr(92), "/")
            if not pathlib.Path(ref).exists():
                print(f"MISSING-PATH {f}:{i} {ref}")
print("=== DATA CROSS-CHECK ===")
def load(name):
    p = pathlib.Path("data") / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f"ERR {e}"
store = load("store_gates.json")
shop = load("shopify_gates.json")
ready = load("ready_gates.json")
final = load("final_gates.json")
scout = load("scout_pool.json")
for nm, d in (("store_gates", store), ("shopify_gates", shop), ("ready_gates", ready), ("final_gates", final), ("scout_pool", scout)):
    if isinstance(d, list):
        keys = sorted({k for g in d if isinstance(g, dict) for k in g})
        print(f"{nm}: {len(d)} records; sample keys={keys[:18]}")
        if d and isinstance(d[0], dict):
            print("   sample:", json.dumps(d[0], ensure_ascii=False)[:280])
    else:
        print(nm, d)
def domains_txt(name):
    p = pathlib.Path("data") / name
    if not p.exists():
        return set()
    return {l.strip().rstrip("/").replace("https://","").replace("http://","") for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
st_txt = domains_txt("store_targets.txt")
sh_txt = domains_txt("shopify_targets.txt")
hit_txt = domains_txt("hit_targets.txt")
st_json = {g.get("domain") for g in store if isinstance(g, dict)} if isinstance(store, list) else set()
sh_json = {g.get("domain") for g in shop if isinstance(shop, dict)} if isinstance(shop, list) else set()
print("store_targets.txt:", len(st_txt), "store_gates.json:", len(st_json), "txt_not_in_json:", sorted(st_txt - st_json))
print("shopify_targets.txt:", len(sh_txt), "shopify_gates.json:", len(sh_json), "txt_not_in_json:", sorted(sh_txt - sh_json))
dead_store = sorted(g.get("domain") for g in store if isinstance(g, dict) and (g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False)) if isinstance(store, list) else []
dead_shop = sorted(g.get("domain") for g in shop if isinstance(g, dict) and (g.get("dead_surface") or g.get("phantom") or g.get("blocked") or g.get("verified") is False)) if isinstance(shop, list) else []
print("dead_store:", len(dead_store), dead_store[:12])
print("dead_shop:", len(dead_shop), dead_shop[:12])
print("dead_shop_still_in_txt:", sorted(set(dead_shop) & sh_txt)[:20])
print("dead_store_still_in_txt:", sorted(set(dead_store) & st_txt)[:20])
print("hit_targets.txt lines:", len(hit_txt), sorted(hit_txt)[:5])
unc_shop = sorted(g.get("domain") for g in shop if isinstance(g, dict) and g.get("needs_live_check") and not g.get("verified")) if isinstance(shop, list) else []
print("needs_live_check(shopify):", len(unc_shop))
