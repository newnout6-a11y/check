# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.loads(pathlib.Path("_audit/_cand32.json").read_text(encoding="utf-8"))
for r in d:
    print("=" * 90)
    print(f"{r['url']}  [{r['status']}]  {r['amount']}c {r['cur']}  {r['ms']}ms")
    print("  detail:", r["detail"])
cat = {str(v.get("domain","")).lower(): v for v in json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))}
print()
for u in [r["url"] for r in d]:
    dom = u.replace("https://","")
    v = cat.get(dom) or {}
    print(f"{dom:26} dead_surface={v.get('dead_surface')} phantom={v.get('phantom')} verified={v.get('verified')} battle={v.get('battle_result')} verify_status={v.get('verify_status')} cheapest={v.get('cheapest_cents')}")
    print(f"{'':26} verify_detail={str(v.get('verify_detail'))[:110]}")
