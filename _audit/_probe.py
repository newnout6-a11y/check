
import sqlite3, os, json, sys
ROOT = r"C:\Users\Redmi\Downloads\pusto"
os.chdir(ROOT)

print("=== History (root) ===")
try:
    c = sqlite3.connect("History")
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    print("  tables:", tabs)
    for t in tabs[:5]:
        try:
            n = c.execute(f"select count(*) from [{t}]").fetchone()[0]
            print(f"    {t}: {n} rows")
            if "url" in t.lower() or t.lower() in ("urls","visits"):
                for r in c.execute(f"select * from [{t}] limit 2"): print("      ", str(r)[:200])
        except Exception as e: print("    err", e)
except Exception as e:
    print("  ERROR:", e)

print()
print("=== data/domains.db ===")
c = sqlite3.connect("data/domains.db")
print("  tables:", [r[0] for r in c.execute("select name from sqlite_master where type='table'")])
for t in [r[0] for r in c.execute("select name from sqlite_master where type='table'")]:
    print(f"    {t}: {c.execute(f'select count(*) from [{t}]').fetchone()[0]} rows")
try:
    print("  by_source:", dict(c.execute("select source,count(*) from domains group by source")))
    print("  by_result:", dict(c.execute("select scan_result,count(*) from domains where scan_result is not null group by scan_result")))
    print("  scanned:", c.execute("select count(*) from domains where last_scanned is not null").fetchone()[0])
except Exception as e: print("  ", e)

print()
print("=== root domains.db ===")
print("  size:", os.path.getsize("domains.db"), "bytes")

print()
print("=== funnel.py ===")
src = open("funnel.py", encoding="utf-8-sig").read().splitlines()
for i,l in enumerate(src[:40],1): print(f"{i:4}\t{l}")
