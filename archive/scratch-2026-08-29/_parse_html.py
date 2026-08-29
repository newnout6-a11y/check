import html
import json
import re

with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
    text = f.read()

print("File length:", len(text))

# Search for serialized data
matches = re.findall(r'data-([a-zA-Z0-9_-]+)=["\'](&quot;\{.*?|&quot;\[.*?)["\']', text)
print(f"Found {len(matches)} JSON data attributes:")
for name, val in matches:
    decoded = html.unescape(val)
    print(f"\n--- data-{name} (len {len(decoded)}) ---")
    try:
        parsed = json.loads(decoded)
        print("Keys:", list(parsed.keys()) if isinstance(parsed, dict) else len(parsed))
        if isinstance(parsed, dict):
            for k in list(parsed.keys())[:10]:
                print(f"  {k}: {str(parsed[k])[:80]}")
    except Exception as e:
        print("Raw snippet:", decoded[:200])

# Search for any other script tags or JSON in the HTML
matches_json = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', text, re.DOTALL)
print(f"\nFound {len(matches_json)} application/json scripts")
for i, s in enumerate(matches_json):
    print(f"JSON script {i} (len {len(s)}): {s[:100]}...")
