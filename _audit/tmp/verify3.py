
import json, re, os, collections
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
src = open("harvest_donors.py", encoding="utf-8").read()
i = src.find("SLUGS")
j = src.find("]", i)
block = src[i:j+1]
print("SLUGS block lines:", block.count(chr(10)))
print("SLUGS entries:", len(re.findall(r'"[^"]+"', block)))
print("tail of block:", block[-200:])
d = json.load(open("data/shopify_gates.json", encoding="utf-8"))
oc = [x for x in d if str(x.get("last_live_verdict","")).startswith("OVER_CAP")]
print("OVER_CAP count:", len(oc))
print("DEAD verdicts:", len([x for x in d if x.get("last_live_verdict")=="DEAD"]))
print("verified True:", len([x for x in d if x.get("verified") is True]))
tiers = collections.Counter()
for x in d:
    c = x.get("cheapest_cents") or 0
    tiers["1" if c < 100 else ("5" if c <= 500 else "20")] += 1
print("tier approx:", tiers)
print("--- proxy interval search ---")
for root, dirs, files in os.walk("."):
    if any(s in root for s in (".git","__pycache__","node_modules",".pytest_cache","_audit",".ruff_cache")): continue
    for f in files:
        if f.endswith(".py"):
            pth = os.path.join(root, f)
            try: txt = open(pth, encoding="utf-8").read()
            except Exception: continue
            for m in re.finditer(r"^.*(900|15 \* 60|proxy_health|autoclean|auto_clean).*$", txt, re.M):
                line = m.group(0).strip()
                if "proxy" in line.lower() and ("900" in line or "clean" in line.lower() or "interval" in line.lower()):
                    print(pth, "|", line[:150])
print("--- proxy.js anchor lines ---")
pj = open("free-buff-lol/proxy.js", encoding="utf-8").read().splitlines()
print("total lines:", len(pj))
for pat in ["class ModelRegistry","class UpstreamClient","class TokenPool","class WarpPlusManager","function normalizeChatMessages","function normalizeToolSchemas","function convertClaudeMessagesRequestToOpenAI","function validateToken","function startServer","function setupOpencodeConfig","async function handleRequest","function parseConstants","function buildModelMapping","function startRunChainNormal","function normalizeSchemaMap","function isSessionInvalid","function isRunInvalid","function readBodyText","function handleHealthz","function authorized"]:
    hits = [k+1 for k,l in enumerate(pj) if pat in l]
    print(pat, "->", hits[:3])
