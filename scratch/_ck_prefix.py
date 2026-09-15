import pathlib, shutil, sqlite3, tempfile, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
src = pathlib.Path(tempfile.gettempdir()) / 'kimi_prof' / 'Default' / 'Network' / 'Cookies'
tmp = pathlib.Path(tempfile.gettempdir()) / '_ck_probe.db'
shutil.copy2(src, tmp)
con = sqlite3.connect(str(tmp)); cur = con.cursor()
cur.execute("select host_key, name, substr(encrypted_value,1,3), length(encrypted_value) from cookies where host_key like '%kimi%' order by name")
print('host | name | префикс шифрования | длина')
for h, n, pre, ln in cur.fetchall():
    try: mark = pre.decode('utf-8', 'replace')
    except Exception: mark = str(pre)
    print(f'  {h:20} {n:34} {mark!r:8} {ln}')
con.close(); tmp.unlink(missing_ok=True)