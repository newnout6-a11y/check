# language: python, file: scratch/_db_stats.py — очередь domains.db одним взглядом
import sqlite3

con = sqlite3.connect("data/domains.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
for t in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n== {t} ({n} rows) cols={cols}")
if "domains" in tables:
    print("\nscan_result breakdown:")
    for row in cur.execute("SELECT COALESCE(scan_result,'NULL'), COUNT(*) FROM domains GROUP BY 1 ORDER BY 2 DESC"):
        print(" ", row)
    print("\nby source:")
    for row in cur.execute("SELECT source, COUNT(*) FROM domains GROUP BY 1"):
        print(" ", row)
