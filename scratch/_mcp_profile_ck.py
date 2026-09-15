import pathlib, shutil, sqlite3, tempfile, sys, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
db = pathlib.Path.home() / '.cache/chrome-devtools-mcp/chrome-profile/Default/Network/Cookies'
print('база MCP-профиля:', db.exists(), db.stat().st_size if db.exists() else 0)
if db.exists():
    tmp = pathlib.Path(tempfile.gettempdir()) / '_mcpck.db'; shutil.copy2(db, tmp)
    con = sqlite3.connect(str(tmp)); cur = con.cursor()
    cur.execute("select count(*) from cookies"); print('cookies всего:', cur.fetchone()[0])
    cur.execute("select host_key, name, length(encrypted_value), creation_utc from cookies where host_key like '%kimi%' or host_key like '%google%' order by creation_utc desc limit 12")
    for h, n, ln, cr in cur.fetchall():
        ts = (datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(cr))).strftime('%Y-%m-%d %H:%M') if cr else '?'
        print(f'  {h:26} {n:30} len={ln:4} создан={ts}')
    con.close(); tmp.unlink(missing_ok=True)