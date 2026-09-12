#!/usr/bin/env python
"""Минимальный клиент Tavily REST для аудита (без инструмента research).
Использование: python _audit/tavily.py "запрос" [max_results]
Ключ: env TVLY_API_KEY или _audit/.tavily_key"""
import json, os, pathlib, sys, urllib.request, urllib.error

KEY = os.environ.get("TVLY_API_KEY", "").strip()
if not KEY:
    kp = pathlib.Path(__file__).with_name(".tavily_key")
    if kp.exists():
        KEY = kp.read_text(encoding="utf-8").strip()

def search(query: str, max_results: int = 5, depth: str = "advanced"):
    body = json.dumps({"query": query, "max_results": max_results,
                       "search_depth": depth, "include_answer": True}).encode()
    req = urllib.request.Request("https://api.tavily.com/search", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "test"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    try:
        d = search(q, n)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:500]); sys.exit(1)
    if d.get("answer"):
        print("ANSWER:", d["answer"][:1200])
    for it in d.get("results", []):
        print("-", it.get("title"))
        print("  ", it.get("url"))
        print("  ", (it.get("content") or "")[:400].replace("\n", " "))
