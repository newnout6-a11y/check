# -*- coding: utf-8 -*-
import json

with open('scratch/_qualify_35_results.json', encoding='utf-8') as f:
    res = json.load(f)

print('Summary of 35 domains:')
verified_live = [r for r in res if r.get('status') == 'VERIFIED_LIVE']
over_cap = [r for r in res if r.get('status') == 'OVER_CAP']
failed = [r for r in res if r.get('status') not in ('VERIFIED_LIVE', 'OVER_CAP')]

print(f'VERIFIED_LIVE (under $20, passed live checkout): {len(verified_live)}')
for r in verified_live:
    print(f"  [+] {r['domain']:30} {r['cheapest_cents']:5}c {r['currency']:4} -> {r['last_live_verdict']}")

print(f"\nOVER_CAP (> $20, catalog known, working): {len(over_cap)}")
for r in over_cap:
    print(f"  [^] {r['domain']:30} {r['cheapest_cents']:5}c {r['currency']:4} -> {r['last_live_verdict']}")

print(f"\nFAILED / UNUSABLE (errors, no products): {len(failed)}")
for r in failed:
    print(f"  [x] {r['domain']:30} {str(r.get('cheapest_cents')):5}  {r['currency']:4} -> {r.get('status')}")
