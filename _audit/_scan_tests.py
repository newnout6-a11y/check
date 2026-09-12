
import ast, os, sys, importlib
ROOT = r"C:\Users\Redmi\Downloads\pusto"
os.chdir(ROOT); sys.path.insert(0, ROOT)

mods = set()
for f in os.listdir(ROOT):
    if f.endswith(".py"): mods.add(f[:-3])
for d in ("bot","bot/gates","bot/utils"):
    p = os.path.join(ROOT, d)
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.endswith(".py"): mods.add(f[:-3])

print("=== BOM / encoding ===")
for d in ("tests","scratch","."):
    for fn in sorted(os.listdir(os.path.join(ROOT,d))):
        if not fn.endswith(".py"): continue
        p = os.path.join(ROOT,d,fn)
        raw = open(p,"rb").read(3)
        if raw == b"\xef\xbb\xbf":
            print(f"  BOM: {d}/{fn}")

def rd(p):
    return open(p, encoding="utf-8-sig").read()

print()
print("=== TEST: mock.patch / setattr targets that do NOT resolve ===")
bad = []
for fn in sorted(os.listdir(os.path.join(ROOT,"tests"))):
    if not fn.endswith(".py"): continue
    src = rd(os.path.join(ROOT,"tests",fn)); tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call): continue
        fname = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else None)
        if fname not in ("patch","setattr","import_module","getattr"): continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value,str)): continue
        tgt = node.args[0].value
        if "." not in tgt: continue
        parts = tgt.split("."); head = parts[0]
        if head not in mods: continue
        try:
            obj = importlib.import_module(parts[0])
            for p in parts[1:]:
                if hasattr(obj,p): obj = getattr(obj,p)
                else: bad.append((fn,node.lineno,tgt,p)); break
        except Exception as e:
            bad.append((fn,node.lineno,tgt,f"{type(e).__name__}: {e}"))
for b in bad: print(f"  {b[0]}:{b[1]}  target={b[2]}  MISSING={b[3]}")
if not bad: print("  (none)")

print()
print("=== TEST: imports of repo modules that fail / attributes missing ===")
mi = []
for fn in sorted(os.listdir(os.path.join(ROOT,"tests"))):
    if not fn.endswith(".py"): continue
    tree = ast.parse(rd(os.path.join(ROOT,"tests",fn)))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level==0:
            if node.module.split(".")[0] in mods:
                try:
                    m = importlib.import_module(node.module)
                    for a in node.names:
                        if a.name!="*" and not hasattr(m,a.name): mi.append((fn,node.lineno,f"from {node.module} import {a.name}"))
                except Exception as e: mi.append((fn,node.lineno,f"import {node.module} -> {type(e).__name__}: {e}"))
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in mods or a.name in mods:
                    try: importlib.import_module(a.name)
                    except Exception as e: mi.append((fn,node.lineno,f"import {a.name} -> {type(e).__name__}: {e}"))
for b in mi: print(f"  {b[0]}:{b[1]}  {b[2]}")
if not mi: print("  (none)")

print()
print("=== SCRATCH: imports of repo modules / sibling scratch modules ===")
sd = os.path.join(ROOT,"scratch")
scratch_names = {f[:-3] for f in os.listdir(sd) if f.endswith(".py")}
for fn in sorted(os.listdir(sd)):
    if not fn.endswith(".py"): continue
    try: tree = ast.parse(rd(os.path.join(sd,fn)))
    except SyntaxError as e: print(f"  {fn}: SYNTAX ERROR {e}"); continue
    probs = []
    sys.path.insert(0, sd)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level==0:
            head = node.module.split(".")[0]
            if head in mods or head in scratch_names:
                try:
                    m = importlib.import_module(node.module)
                    for a in node.names:
                        if a.name!="*" and not hasattr(m,a.name): probs.append(f"from {node.module} import {a.name} (name gone)")
                except Exception as e: probs.append(f"import {node.module} -> {type(e).__name__}: {e}")
        if isinstance(node, ast.Import):
            for a in node.names:
                head=a.name.split(".")[0]
                if head in mods or head in scratch_names:
                    try: importlib.import_module(a.name)
                    except Exception as e: probs.append(f"import {a.name} -> {type(e).__name__}: {e}")
    sys.path.remove(sd)
    if probs: print(f"  {fn}: " + " | ".join(probs))
