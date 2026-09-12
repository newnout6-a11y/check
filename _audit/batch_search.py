import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from tavily import search
for q in sys.argv[1:]:
    try:
        d = search(q, 4)
    except Exception as e:
        print("=== " + q + "\n  ERR " + str(e)[:200]); continue
    print("=== " + q)
    if d.get("answer"):
        print("  ANSWER: " + d["answer"][:600].replace("\n", " "))
    for it in d.get("results", [])[:3]:
        print("  - " + (it.get("title") or "")[:110] + " | " + (it.get("url") or ""))
        print("    " + ((it.get("content") or "")[:280]).replace("\n", " "))
