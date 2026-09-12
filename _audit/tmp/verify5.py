
import json, re, os
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
src = open("free-buff-lol/proxy.js", encoding="utf-8").read()
low = src.lower()
for pat in ["warp", "8086", "socks", "vbs", "cscript", "msgbox", "proxyagent", "undici", "require('undici')", "node-forge"]:
    idxs = [m.start() for m in re.finditer(re.escape(pat), low)]
    print("%-18s count=%d" % (pat, len(idxs)))
print("--- version tracking block 100-180 ---")
print(chr(10).join("%d: %s" % (i+1, l) for i, l in enumerate(src.splitlines()[99:180], start=99)))
print("--- model map block 800-860 ---")
print(chr(10).join("%d: %s" % (i+1, l) for i, l in enumerate(src.splitlines()[824:850], start=824)))
print("--- mcp.json ---")
print(open(".agents/mcp.json", encoding="utf-8").read()[:2000])
