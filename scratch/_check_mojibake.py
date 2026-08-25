# language: Python 3.12+, file: scratch/_check_mojibake.py, target: Windows 11
import sys

for f in ["config.py", "confirm_gate.py", "bot/main.py", "gate_client.py"]:
    t = open(f, encoding="utf-8").read()
    # кириллица в UTF-8 = U+04xx; mojibake-артефакты = U+00C0-U+00FF россыпью
    cyr = sum(1 for c in t if "\u0400" <= c <= "\u04ff")
    latin_ext = sum(1 for c in t if "\u00c0" <= c <= "\u00ff")
    print(f"{f}: cyr={cyr} latin-ext={latin_ext} -> {'OK' if latin_ext < 10 else 'MOJIBAKE'}")
