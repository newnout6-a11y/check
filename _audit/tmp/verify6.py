
import re, os
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
lines = open("free-buff-lol/proxy.js", encoding="utf-8").read().splitlines()
for pat in ["BUN_VERSION", "FREEBUFF_CLI_VERSION", "AI_SDK_COMPAT_VERSION", "CODEBUFF_JSON_USER_AGENT", "FREEBUFF_CLI_USER_AGENT", "getApiUserAgent", "getChatUserAgent", "getAdsUserAgent", "chatCompletions", "Request timeout", "NPM_PACKAGE_NAME", "FREEBUFF2API_RS_SOURCE"]:
    hits = [(k+1, lines[k].strip()[:120]) for k in range(len(lines)) if pat in lines[k]]
    print(pat, len(hits))
    for h in hits[:8]: print("   ", h[0], h[1])
