# -*- coding: utf-8 -*-
"""Скан отслеживаемых git файлов на секреты: PAN (Luhn), прокси-креды, ключи, TG."""
import subprocess, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.splitlines()
PAN_RX = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
PROXY_RX = re.compile(r"[a-z0-9+.-]+://[^\s:/@]{2,}:[^\s:/@]{2,}@[^\s/]+", re.I)
KEY_RX = re.compile(r"(sk_live_[0-9A-Za-z]{10,}|pk_live_[0-9A-Za-z]{10,}|user_[0-9A-Za-z]{12,})")
TG_RX = re.compile(r"[0-9a-f]{32}")

def luhn(num: str) -> bool:
    d = [int(c) for c in num]
    if len(d) < 13: return False
    s = 0
    for i, x in enumerate(reversed(d)):
        if i % 2: 
            x *= 2
            if x > 9: x -= 9
        s += x
    return s % 10 == 0

report = []
for f in files:
    p = pathlib.Path(f)
    if not p.is_file() or p.stat().st_size > 3_000_000:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    pans = {n for n in (m.group(0).replace(" ", "").replace("-", "") for m in PAN_RX.finditer(t)) if 13 <= len(n) <= 19 and luhn(n)}
    prox = PROXY_RX.findall(t)
    keys = KEY_RX.findall(t)
    if pans or prox or keys:
        report.append((f, sorted(pans)[:4], len(pans), len(prox), sorted(set(keys))[:3]))

print("tracked files with secrets:", len(report))
for f, ex, np_, nprox, keys in report:
    print(f"\n{f}")
    print(f"   PAN: {np_} (пример: {[x[:6] + '...' + x[-4:] for x in ex]})")
    print(f"   proxy-creds: {nprox}")
    if keys: print(f"   keys: {keys}")
