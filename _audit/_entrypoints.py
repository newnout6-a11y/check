
import pathlib, re
root = pathlib.Path(".")
eps = []
for p in sorted(root.glob("*.py")):
    t = p.read_text(encoding="utf-8", errors="replace")
    if '__name__ == "__main__"' in t or "if __name__" in t:
        eps.append(p.name)
print("root .py with __main__ guard:", len(eps))
print(", ".join(eps))
# also any argparse-based CLIs
arg = [p.name for p in sorted(root.glob("*.py")) if "argparse" in p.read_text(encoding="utf-8", errors="replace")]
print("root .py using argparse:", len(arg), "->", ", ".join(arg))
