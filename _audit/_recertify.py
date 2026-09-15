# -*- coding: utf-8 -*-
"""Снятие устаревших флагов dead_surface/phantom у переаттестованных боем доменов."""
import json, pathlib, time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = pathlib.Path("data/store_gates.json")
gates = json.loads(P.read_text(encoding="utf-8"))
RECERT = {
    "madatshop.com": ("DECLINED", 190),
    "herbaura.fr": ("DECLINED", 890),
    "cherryarts.org": ("DECLINED", 1200),
}
stamp = "2026-09-12"
changed = []
for g in gates:
    d = str(g.get("domain", "")).lower()
    if d in RECERT:
        verdict, cents = RECERT[d]
        before = (g.get("dead_surface"), g.get("phantom"))
        g["dead_surface"] = False
        g["phantom"] = False
        g["recertified_at"] = stamp
        g["recertified_verdict"] = verdict
        g["recertified_detail"] = f"боевой прогон {stamp}: полный цикл, вердикт процессора {verdict} ({cents}c)"
        g["cheapest_cents"] = cents
        g["battle_result"] = "LIVE (cap $20)"
        g["updated_at"] = int(time.time())
        changed.append((d, before, (g["dead_surface"], g["phantom"])))
P.write_text(json.dumps(gates, ensure_ascii=False, indent=2), encoding="utf-8")
print("переаттестованы:", changed)
