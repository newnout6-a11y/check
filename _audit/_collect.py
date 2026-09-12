
import subprocess, sys, collections, pathlib
py = r"C:\Users\Redmi\AppData\Local\Python\pythoncore-3.14-64\python.exe"
out = subprocess.run([py, "-m", "pytest", "tests/", "--collect-only", "-q"], capture_output=True, text=True, cwd=r"C:\Users\Redmi\Downloads\pusto")
lines = [l for l in out.stdout.splitlines() if "::" in l]
c = collections.Counter(l.split("::")[0] for l in lines)
total = sum(c.values())
print("TOTAL COLLECTED:", total, " FILES WITH TESTS:", len(c))
for k in sorted(c):
    print(f"  {k:46} {c[k]}")
print("test_*.py on disk:", len(sorted(pathlib.Path(r'C:\Users\Redmi\Downloads\pusto\tests').glob('test_*.py'))))
