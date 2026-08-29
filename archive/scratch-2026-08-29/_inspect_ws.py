with open("scratch/_checkout_app.js", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

pos = 1300716
snippet = text[max(0, pos - 500):min(len(text), pos + 1500)]
print("Snippet around WS / handle_next_action:")
print(snippet)
