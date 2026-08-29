import re

with open("scratch/_checkout_app.js", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

print(f"Total bundle size: {len(text)} chars")

keywords = [
    "next_action",
    "use_stripe_sdk",
    "three_d_secure_2",
    "3ds2/authenticate",
    "3ds2/challenge_complete",
    "three_d_secure_redirect",
    "three_d_secure_2_source",
    "handleCardAction",
    "handleNextAction",
    "transStatus",
]

for kw in keywords:
    matches = [m.start() for m in re.finditer(re.escape(kw), text)]
    print(f"Keyword '{kw}': {len(matches)} occurrences")
    for pos in matches[:3]:
        snippet = text[max(0, pos - 150):min(len(text), pos + 250)]
        print(f"  [{pos}] ...{snippet}...\n")
