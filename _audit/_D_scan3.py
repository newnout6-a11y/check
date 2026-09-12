import sys, pathlib
sys.path.insert(0, ".")
import re, json
exec(open("_audit/_D_scan2.py", encoding="utf-8").read().split('print("=== CALLBACK')[0].replace('import re, pathlib, json',''))
mn = pathlib.Path("bot/main.py").read_text(encoding="utf-8")
kb = pathlib.Path("bot/keyboards.py").read_text(encoding="utf-8")
print("=== CALLBACK HANDLER CHECK v2 ===")
for cb in sorted(set(re.findall(r'callback_data="([^"]+)"', kb))):
    ok = (f'data == "{cb}"' in mn) or (f'data == \'{cb}\'' in mn) or ('data.startswith("%s' % cb.rsplit(":",1)[0] + ':"' in mn)
    print(("OK   " if ok else "DEAD "), cb)
print("=== VERDICT INVENTORY vs config.VERDICTS ===")
import config
scope = ["setup_gate.py","store_gate.py","shopify_gate.py","hit_gate.py","confirm_gate.py"] + \
        [str(p).replace(chr(92), "/") for p in pathlib.Path("bot").rglob("*.py")]
cand = {}
for f in scope:
    p = pathlib.Path(f)
    if not p.exists(): continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r'"(?:status|verdict)"\s*:\s*"([^"]+)"', line):
            cand.setdefault(m.group(1), []).append(f"{f}:{i}")
        for m in re.finditer(r'return\s+"([A-Z][A-Z0-9_@]{2,})"', line):
            cand.setdefault(m.group(1), []).append(f"{f}:{i}")
known = set(config.VERDICTS)
for v, locs in sorted(cand.items()):
    if v not in known:
        print(f"OUT-OF-TAXONOMY {v} <- {locs[0]} -> coerced {config.coerce_verdict(v)}")
