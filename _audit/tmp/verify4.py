
import re, os, json, collections, subprocess, sys
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
pj = open("free-buff-lol/proxy.js", encoding="utf-8").read()
for pat in ["WarpPlus", "parseConstants", "buildModelMapping", "SUPPORTED_MODELS", "CANONICAL_MODEL_ALIASES", "FALLBACK_AGENT_IDS", "BLACKLISTED_MODEL_PATTERNS"]:
    lines = [k+1 for k,l in enumerate(pj.splitlines()) if pat in l]
    print(pat, "occurrences:", len(lines), "first:", lines[:5])
i = pj.find("SUPPORTED_MODELS")
print(pj[i-200:i+700])
print("=== mcp / agent dirs ===")
for d in [".agents", ".freebuff", ".workbuddy-ai"]:
    for root, dirs, files in os.walk(d):
        for f in files:
            print(os.path.join(root, f))
