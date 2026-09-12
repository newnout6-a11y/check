
import re, os
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
src = open("free-buff-lol/proxy.js", encoding="utf-8").read()
lines = src.splitlines()
for pat in ["exit(42)", "process.exit", "pathname ===", "'/api/keys'", "handleHealthz", "handleDashboard", "/dashboard", "warp", "dummy", "42"]:
    hits = [(k+1, lines[k].strip()[:140]) for k in range(len(lines)) if pat in lines[k]]
    print("== %s : %d" % (pat, len(hits)))
    for h in hits[:10]: print("   ", h[0], h[1])
