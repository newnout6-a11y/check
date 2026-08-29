# -*- coding: utf-8 -*-
# Инвентарь chati/: домены, платформы, доноры из экспортов телеграм-чатов
import os, re, sys
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")

CH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chati")
files = [f for f in os.listdir(CH) if f.startswith("search_") and f.endswith(".txt")]

url_re = re.compile(r"https?://([a-zA-Z0-9][-a-zA-Z0-9.]*.[a-zA-Z]{2,})(/S*)?")
SKIP = {"t.me", "telegram.org", "youtube.com", "youtu.be", "google.com", "github.com",
        "i.imgur.com", "imgur.com", "gstatic.com", "tenor.com", "spotify.com",
        "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com",
        "whatsapp.com", "discord.com", "discord.gg", "pastebin.com", "soundcloud.com",
        "wikipedia.org", "reddit.com", "fonts.googleapis.com", "prnt.sc", "ibb.co"}

domains = Counter()
adyen_links = set()
stripe_cs = set()
opus_links = set()
total_msgs = 0
for fn in files:
    with open(os.path.join(CH, fn), encoding="utf-8", errors="ignore") as f:
        txt = f.read()
    total_msgs += txt.count("Сообщение #")
    for m in url_re.finditer(txt):
        d = m.group(1).lower()
        if d in SKIP or any(d.endswith("." + s) for s in SKIP):
            continue
        domains[d] += 1
        rest = (m.group(2) or "")
        if d == "eu.adyen.link" or d.endswith(".adyen.link"):
            adyen_links.add(d + rest[:40])
        if "cs_live_" in rest:
            stripe_cs.add(d)
            if d == "pay.opus.pro":
                opus_links.add(m.group(0)[:80])

print(f"файлов: {len(files)}, сообщений: {total_msgs}")
print(f"\n=== ТОП-40 доменов (без соцсетей) ===")
for d, c in domains.most_common(40):
    print(f"  {c:5}  {d}")
print(f"\n=== adyen.link ссылок: {len(adyen_links)} (примеры) ===")
for l in list(adyen_links)[:6]:
    print("  " + l)
print(f"\n=== домены с cs_live (stripe checkout): {stripe_cs}")
print(f"=== opus.pro чекаутов: {len(opus_links)} (примеры) ===")
for l in list(opus_links)[:3]:
    print("  " + l)
