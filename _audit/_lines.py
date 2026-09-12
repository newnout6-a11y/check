
import pathlib
root = pathlib.Path(".")
files = sorted([p for p in root.glob("*.py")]) + [root/"bot/main.py", root/"bot/gates/shopify.py"]
for p in files:
    n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    print(f"{str(p).replace(chr(92),'/'):34} {n}")
print("tests files:", len(list((root/'tests').glob('*.py'))))
print("scratch files:", len(list((root/'scratch').glob('*.py'))))
