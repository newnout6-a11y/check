with open("scratch/_stripe_v3.js", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'authenticate3DS2', text)]
print(f"Matches for 'authenticate3DS2': {len(matches)}")
for pos in matches:
    print(f"\n--- At {pos} ---")
    print(text[max(0, pos - 200):min(len(text), pos + 1500)])
