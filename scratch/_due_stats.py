# language: python, file: scratch/_due_stats.py — сколько доменов due для основного сканера
import sqlite3
import time

con = sqlite3.connect("data/domains.db")
cur = con.cursor()
cutoff = int(time.time()) - 24 * 3600
print("due 24h:", cur.execute(
    "SELECT COUNT(*) FROM domains WHERE last_scanned IS NULL OR last_scanned < ?",
    (cutoff,)).fetchone()[0])
print("store_live:", cur.execute(
    "SELECT COUNT(*) FROM domains WHERE scan_result='STORE_LIVE'").fetchone()[0])
print("never scanned:", cur.execute(
    "SELECT COUNT(*) FROM domains WHERE last_scanned IS NULL").fetchone()[0])
