import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

print("=== ALL META TAGS ===")
for meta in soup.find_all("meta"):
    name = meta.get("name") or meta.get("property") or meta.get("http-equiv")
    content = meta.get("content")
    if name and name.startswith("serialized-"):
        print(f"\n--- {name} ---")
        try:
            val = json.loads(content)
            if isinstance(val, (dict, list)):
                print(json.dumps(val, indent=2, ensure_ascii=False)[:500])
            else:
                print(str(val)[:120])
        except Exception:
            print(content[:120])
    elif name:
        print(f"{name}: {str(content)[:80]}")
