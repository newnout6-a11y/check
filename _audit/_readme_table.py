
import re, pathlib
t = pathlib.Path("README.md").read_text(encoding="utf-8")
sec = t.split("## 10. Тесты", 1)[1].split("## 11.", 1)[0]
rows = re.findall(r"\|\s*`(tests/[a-z0-9_]+)\.py`\s*\|\s*(\d+)\s*\|", sec)
print("rows in README §10 table:", len(rows))
print("sum of README numbers:", sum(int(n) for _, n in rows))
hdr = re.search(r"\*\*(\d+) passed\*\* \((\d+) файл", sec)
print("claimed in header:", hdr.groups() if hdr else None)
disk = sorted(p.stem for p in pathlib.Path("tests").glob("test_*.py"))
listed = sorted(n.split("/")[1] for n, _ in rows)
print("files on disk:", len(disk), "| listed in table:", len(listed))
print("on disk but NOT in table:", [d for d in disk if d not in listed])
print("in table but NOT on disk:", [d for d in listed if d not in disk])
