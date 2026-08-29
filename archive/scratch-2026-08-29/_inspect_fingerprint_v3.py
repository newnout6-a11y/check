with open("scratch/_stripe_v3.js", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

pos = 948254
snippet = text[max(0, pos - 1000):min(len(text), pos + 3000)]
print("Snippet around 3ds2-fingerprint:")
print(snippet)
