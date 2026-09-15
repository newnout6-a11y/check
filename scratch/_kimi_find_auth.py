import pathlib, shutil, sqlite3, sys, tempfile, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
try:
    import cryptography; print('cryptography:', cryptography.__version__)
except Exception as e:
    print('cryptography НЕТ:', type(e).__name__)
try:
    from Crypto.Cipher import AES; print('pycryptodome: есть')
except Exception as e:
    print('pycryptodome нет')
base = pathlib.Path.home() / 'AppData/Local/Google/Chrome/User Data'
def chrome_ts(us):
    if not us: return None
    return datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(us))
for prof in [p for p in base.iterdir() if p.is_dir() and (p.name=='Default' or p.name.startswith('Profile '))]:
    db = prof / 'Network' / 'Cookies'
    if not db.exists(): continue
    tmp = pathlib.Path(tempfile.gettempdir()) / '_q.db'
    try: shutil.copy2(db, tmp)
    except Exception as e: print(prof.name, 'копия не удалась', type(e).__name__); continue
    try:
        con = sqlite3.connect(str(tmp)); cur = con.cursor()
        cur.execute("select name, host_key, length(encrypted_value), creation_utc, expires_utc, is_httponly, is_secure, has_expires from cookies where name='kimi-auth' order by creation_utc desc")
        rows = cur.fetchall(); con.close()
        if rows:
            for r in rows:
                print(f'  {prof.name}: kimi-auth host={r[1]} len={r[2]} создан={chrome_ts(r[3])} истекает={chrome_ts(r[4])} httpOnly={r[5]} secure={r[6]} hasExp={r[7]}')
    except Exception as e:
        print(prof.name, 'чтение не удалось', type(e).__name__)
    finally:
        tmp.unlink(missing_ok=True)