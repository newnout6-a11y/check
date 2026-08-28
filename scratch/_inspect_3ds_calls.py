import re

with open("scratch/_checkout_app.js", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

keywords = ["3ds2/authenticate", "stripe_3ds2_fingerprint", "three_d_secure_2_source", "payatt_"]

for kw in keywords:
    matches = [m.start() for m in re.finditer(re.escape(kw), text)]
    print(f"Keyword '{kw}': {len(matches)} occurrences")
    for pos in matches[:3]:
        snippet = text[max(0, pos - 200):min(len(text), pos + 400)]
        print(f"  [{pos}] ...{snippet}...\n")
