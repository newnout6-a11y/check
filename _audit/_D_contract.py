# language: Python 3.14, file: _audit/_D_contract.py
import ast, pathlib, sys, re, json
sys.path.insert(0, ".")
import config

print("=== GATE MODULE CONTRACT (NAME / COST / gate() arity) ===")
for p in sorted(pathlib.Path("bot/gates").glob("*.py")):
    if p.name == "__init__.py":
        continue
    tree = ast.parse(p.read_text(encoding="utf-8"))
    name = cost = None
    gsig = None
    rets = []
    sem = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            t = node.targets[0].id
            if t == "NAME":
                name = getattr(node.value, "value", None)
            if t == "COST":
                cost = getattr(node.value, "value", None)
            if t == "_sem":
                sem = ast.unparse(node.value)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "gate":
            gsig = f"gate({', '.join(a.arg for a in node.args.args)}) args={len(node.args.args)} kwarg={node.args.kwarg.arg if node.args.kwarg else None}"
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    v = sub.value
                    if isinstance(v, ast.Tuple):
                        rets.append((sub.lineno, f"tuple[{len(v.elts)}]"))
                    elif isinstance(v, ast.Dict):
                        rets.append((sub.lineno, "dict"))
                    else:
                        rets.append((sub.lineno, type(v).__name__))
    print(f"{p.name}: NAME={name} COST={cost} _sem={sem} {gsig}")
    print("    returns:", rets)

print()
print("=== VERDICT LITERALS OUTSIDE config.VERDICTS (gates + engines) ===")
known = set(config.VERDICTS)
targets = [str(p).replace(chr(92), "/") for p in pathlib.Path("bot/gates").glob("*.py")] + \
          ["setup_gate.py", "store_gate.py", "shopify_gate.py", "hit_gate.py", "confirm_gate.py"]
seen = {}
for f in targets:
    fp = pathlib.Path(f)
    if not fp.exists():
        continue
    for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r'"([A-Z][A-Z0-9_@]{3,})"', line):
            v = m.group(1)
            if v in known or v in ("NAME", "COST", "READY", "STALE", "STORE_LIVE", "HTTP"):
                continue
            if re.search(r'"(status|verdict)"\s*:\s*"' + re.escape(v) + '"', line) or re.search(r'return\s*(?:\()?\s*"' + re.escape(v) + '"', line):
                seen.setdefault(v, []).append(f"{f}:{i}")
for v, locs in sorted(seen.items()):
    print(f"  {v:22} -> {config.coerce_verdict(v):10} {locs[0]}  ({len(locs)} мест)")

print()
print("=== ENGINES: return arity used by gates ===")
for f in ("store_gate.py", "shopify_gate.py", "confirm_gate.py"):
    txt = pathlib.Path(f).read_text(encoding="utf-8")
    print(f, "check_target signature:", re.search(r"async def check_target\(([^)]*)\)", txt).group(1).replace("\n", " ")[:120])
print("bot/gates/__init__ registry keys:", [l.strip() for l in pathlib.Path("bot/gates/__init__.py").read_text(encoding="utf-8").splitlines() if "registry[" in l or "cost" in l])
print("config.GATE_COST:", config.GATE_COST if hasattr(config, "GATE_COST") else "n/a")
import importlib
bcfg = importlib.import_module("bot.config")
print("bot.config.GATE_COST:", bcfg.GATE_COST)
print("GATE_PRIORITY in main.py:", re.search(r"GATE_PRIORITY = \[([^]]*)\]", pathlib.Path("bot/main.py").read_text(encoding="utf-8")).group(1).replace("\n", " "))
print("run_gate unpack:", [l.strip() for l in pathlib.Path("bot/main.py").read_text(encoding="utf-8").splitlines() if "res[2] if len(res)" in l])
print("cmd_mass unpack:", [l.strip() for l in pathlib.Path("bot/main.py").read_text(encoding="utf-8").splitlines() if "verdict, detail = engine_cfg.coerce_verdict(res[0])" in l])
