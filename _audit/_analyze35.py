# -*- coding: utf-8 -*-
"""Разбор отчёта прогона 35 магазинов: корректная классификация статусов."""
import json, pathlib, sys, collections
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config

rep = sorted(pathlib.Path("data/results").glob("check35_*.json"))[-1]
d = json.loads(rep.read_text(encoding="utf-8"))
print("отчёт:", rep.name, "| прогонов:", d["total"])
print()
rows = d["results"]
clean_names = lambda s: s.startswith(("DECLINED", "APPROVED", "3DS")) or s in ("PI_PENDING","RATE_LIMITED","WRONG_CVC","RESTRICTED","INVALID","EXPIRED")
clean = [r for r in rows if clean_names(r["status"])]
technical = [r for r in rows if not clean_names(r["status"])]
unknown = [r for r in rows if config.coerce_verdict(r["status"]) == "UNKNOWN"]
unrefundable_error = [r for r in rows if config.coerce_verdict(r["status"]) == "ERROR" and not config.is_refundable(r["status"])]

print("=== КЛАССИФИКАЦИЯ (по контракту config.coerce_verdict / is_refundable) ===")
print(f"чистых вердиктов процессора : {len(clean)}")
print(f"технических сбоев (ERROR)   : {len(technical)} — все refundable: {all(config.is_refundable(r['status']) for r in technical)}")
print(f"UNKNOWN (потерянный вердикт): {len(unknown)}")
print(f"ERROR без возврата кредита  : {len(unrefundable_error)}")
print()
print("=== ПО СТАТУСАМ ===")
for st, n in collections.Counter(r["status"] for r in rows).most_common():
    print(f"  {config.icon(st)} {st:18} {n:3}  -> coerce={config.coerce_verdict(st):9} refund={config.is_refundable(st)}")
print()
print("=== ТЕХНИЧЕСКИЕ СБОИ: кто именно ===")
for r in sorted(technical, key=lambda r: r["status"]):
    print(f"  {r['kind']:5} {r['target'][:44]:44} {r['status']:16} {r['detail'][:60]}")
print()
print("=== ПО ПЛАТФОРМАМ ===")
for kind in ("store", "shopify"):
    sub = [r for r in rows if r["kind"] == kind]
    ok = [r for r in sub if clean_names(r["status"])]
    print(f"  {kind:7} всего {len(sub):3} | чистых {len(ok):3} | технических {len(sub)-len(ok):2} | медиана {sorted(r['latency_ms'] for r in sub)[len(sub)//2]}ms")
print()
lat = sorted(r["latency_ms"] for r in rows)
print(f"латентность: min {lat[0]}ms | медиана {lat[len(lat)//2]}ms | max {lat[-1]}ms")
