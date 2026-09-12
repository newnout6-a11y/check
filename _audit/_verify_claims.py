
import json, re, pathlib
p = pathlib.Path("free-buff-lol/proxy.js").read_text(encoding="utf-8", errors="replace")
for k in ["warp", "WarpPlus", "8086", "SocksProxyAgent", "socks", "node-forge", "undici", "https-proxy-agent", "You are Buffy"]:
    print(f"proxy.js {k:20} {p.count(k)}")
for m in re.finditer(r"(BUN_VERSION|FREEBUFF_CLI_VERSION|PROXY_VERSION)\s*=\s*[^;]{0,40}", p):
    print("const:", m.group(0).strip()[:80])
i = p.find("You are Buffy")
print("Buffy ctx:", p[i:i+170].replace("\n"," ") if i >= 0 else "not found")
hd = pathlib.Path("harvest_donors.py").read_text(encoding="utf-8")
for name in ["PRIORITY_SLUGS", "SLUGS"]:
    m = re.search(name + r"\s*=\s*\[(.*?)\]", hd, re.S)
    print(name, "count:", len(re.findall(r'"([^"]+)"', m.group(1))) if m else "n/a")
sh = json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))
print("shopify total", len(sh),
      "| verified", sum(1 for v in sh if v.get("verified")),
      "| price>2000 any", sum(1 for v in sh if (v.get("cheapest_cents") or 0) > 2000),
      "| verified&>2000", sum(1 for v in sh if v.get("verified") and (v.get("cheapest_cents") or 0) > 2000),
      "| unverified", sum(1 for v in sh if not v.get("verified")),
      "| verdict DEAD", sum(1 for v in sh if str(v.get("last_live_verdict","")).upper() == "DEAD"))
sg = json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))
print("store entries", len(sg), "| verified true", sum(1 for v in sg if v.get("verified") is True))
