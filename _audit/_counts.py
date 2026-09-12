
import json, pathlib, collections
d = pathlib.Path("data")
def lines(p):
    t = (d/p).read_text(encoding="utf-8", errors="replace")
    return [x.strip() for x in t.splitlines() if x.strip() and not x.strip().startswith("#")]
def dom(x):
    if isinstance(x, dict):
        for k in ("domain","url","target","root","host","site"):
            if x.get(k): x = x[k]; break
        else: x = str(x.get("id","")) or str(x)[:40]
    x = str(x).strip().rstrip("/")
    return x.replace("https://","").replace("http://","").split("/")[0].lower()

sg = json.loads((d/"store_gates.json").read_text(encoding="utf-8"))
sh = json.loads((d/"shopify_gates.json").read_text(encoding="utf-8"))
print("store_gates sample keys:", sorted(sg[0].keys())[:18])
print("shopify_gates sample keys:", sorted(sh[0].keys())[:22])
print("store_gates statuses:", dict(collections.Counter(v.get("status") for v in sg)))
print("store_gates verified:", dict(collections.Counter(v.get("verified") for v in sg)))
print("store_gates blocked:", dict(collections.Counter(v.get("blocked") for v in sg)))
print("shopify statuses:", dict(collections.Counter(v.get("status") for v in sh)))
print("shopify verified:", dict(collections.Counter(v.get("verified") for v in sh)))
print("shopify with variant_id:", sum(1 for v in sh if v.get("variant_id")))
st_t = {dom(x) for x in lines("store_targets.txt")}
sp_t = {dom(x) for x in lines("shopify_targets.txt")}
sg_d = {dom(v) for v in sg}
sh_d = {dom(v) for v in sh}
print("store target sample:", sorted(st_t)[:5])
print("store_targets not in store_gates:", len(st_t - sg_d), sorted(st_t - sg_d)[:8])
print("store_gates not in store_targets:", len(sg_d - st_t))
print("shopify_targets not in shopify_gates:", len(sp_t - sh_d))
print("shopify_gates not in shopify_targets:", len(sh_d - sp_t))
dup_s = [k for k,c in collections.Counter(dom(v) for v in sg).items() if c>1]
dup_h = [k for k,c in collections.Counter(dom(v) for v in sh).items() if c>1]
print("dup store domains:", dup_s)
print("dup shopify domains:", dup_h)
