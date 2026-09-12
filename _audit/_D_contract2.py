# language: Python 3.14, file: _audit/_D_contract2.py
import pathlib, re, sys
sys.path.insert(0, ".")
import config
mn = pathlib.Path("bot/main.py").read_text(encoding="utf-8")
print("=== callers' unpacking of gate result ===")
for i, line in enumerate(mn.splitlines(), 1):
    if re.search(r"res\[2\]|res\[0\]|len\(res\)", line):
        print(f"  main.py:{i}: {line.strip()[:150]}")
print()
print("=== confirm_gate / store_gate / shopify_gate check_target ===")
for f in ("confirm_gate.py", "store_gate.py", "shopify_gate.py"):
    t = pathlib.Path(f).read_text(encoding="utf-8")
    m = re.search(r"async def check_target\(([^)]*)\)", t, re.S)
    print(" ", f, "->", " ".join(m.group(1).split()) if m else "НЕТ check_target")
print()
print("=== engines return shape check ===")
for f in ("store_gate.py", "shopify_gate.py", "confirm_gate.py"):
    t = pathlib.Path(f).read_text(encoding="utf-8")
    print(" ", f, "returns dict:", t.count('"status":'))
print()
print("=== ALL UPPERCASE VERDICT-LIKE LITERALS in bot/gates + engines, NOT in config.VERDICTS ===")
known = set(config.VERDICTS)
files = [str(p).replace(chr(92), "/") for p in pathlib.Path("bot/gates").glob("*.py")] + \
        ["setup_gate.py", "store_gate.py", "shopify_gate.py", "hit_gate.py", "confirm_gate.py"]
hits = {}
for f in files:
    fp = pathlib.Path(f)
    if not fp.exists(): continue
    for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r'["\']([A-Z][A-Z0-9_@]{2,})["\']', line):
            v = m.group(1)
            if v in known: continue
            hits.setdefault(v, []).append(f"{f}:{i}")
for v, locs in sorted(hits.items(), key=lambda kv: -len(kv[1])):
    print(f"  {v:26} coerced->{config.coerce_verdict(v):9} n={len(locs):2}  first={locs[0]}")
print()
print("=== registry code (bot/gates/__init__.py) ===")
print("  ", [l.strip() for l in pathlib.Path("bot/gates/__init__.py").read_text(encoding="utf-8").splitlines() if "registry" in l or "hasattr" in l])
