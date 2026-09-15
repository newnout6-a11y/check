# language: Python 3.12+, file: scratch/_kimi_refresh.py
import datetime, os, pathlib, shutil, sqlite3, subprocess, sys, tempfile, time, json, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
UD = pathlib.Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/User Data'
src_db = UD / 'Profile 8' / 'Network' / 'Cookies'
def read_rows(db):
    uri = f'file:{db.as_posix()}?mode=ro'
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    cur.execute("select name, length(encrypted_value), creation_utc, expires_utc from cookies where name='kimi-auth'")
    rows = cur.fetchall(); con.close(); return rows
def ts(us):
    return (datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(us))).strftime('%Y-%m-%d %H:%M:%S') if us else '?'
print('=== kimi-auth в РЕАЛЬНОМ Profile 8 (живой профиль) ===')
try:
    for n, ln, cr, ex in read_rows(src_db):
        print(f'  длина={ln} создан={ts(cr)} истекает={ts(ex)}')
except Exception as e:
    print('  чтение не удалось:', type(e).__name__, e)
print('=== kimi-auth в копии C:\\ChromeKimi (с которой сейчас открыт браузер) ===')
cp_db = pathlib.Path('C:/ChromeKimi/Profile 8/Network/Cookies')
try:
    for n, ln, cr, ex in read_rows(cp_db):
        print(f'  длина={ln} создан={ts(cr)} истекает={ts(ex)}')
except Exception as e:
    print('  чтение не удалось:', type(e).__name__)