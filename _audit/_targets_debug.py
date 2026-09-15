# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from bot.gates import storegate
raw = [l.strip() for l in pathlib.Path("data/store_targets.txt").read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")]
print("http-строк в файле:", len(raw))
print("последние 6:", raw[-6:])
dead = storegate._dead_domains()
print("dead-набор:", len(dead))
new = ["madatshop.com","herbaura.fr","cherryarts.org","theposhpundit.co.uk"]
print("в dead?", {d: (d in dead) for d in new})
cat = {str(v.get("domain","")).lower(): v for v in json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))}
for d in new:
    v = cat.get(d)
    print(f"  {d:26} verified={v.get('verified')} dead_surface={v.get('dead_surface')} phantom={v.get('phantom')} battle={v.get('battle_result')}")
t = storegate._targets()
print("_targets() ->", len(t))
print("отфильтрованы:", [x for x in raw if x.replace('https://','') not in [y.replace('https://','') for y in t]])
