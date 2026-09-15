# language: Python 3.12+, file: scratch/_kimi_profile_test.py
import os, pathlib, shutil, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
UD = pathlib.Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/User Data'
tmp = pathlib.Path(tempfile.gettempdir()) / 'kimi_prof'
if tmp.exists():
    shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True)
shutil.copy2(UD / 'Local State', tmp / 'Local State')
src = UD / 'Profile 8'
dst = tmp / 'Default'
rc = os.system(f'robocopy "{src}" "{dst}" /E /NFL /NDL /NJH /NJS /NP >NUL')
print('robocopy код:', rc, '| скопировано в', tmp)
print('файлов в копии:', sum(1 for _ in dst.rglob('*') if _.is_file()))
cookies_db = dst / 'Network' / 'Cookies'
print('Cookie DB в копии:', cookies_db.exists(), cookies_db.stat().st_size if cookies_db.exists() else 0)

from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(tmp), channel='chrome', headless=True,
        args=['--no-first-run', '--no-default-browser-check', '--disable-blink-features=AutomationControlled'],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(3000)
    text = page.inner_text('body')[:300].replace(chr(10), ' ')
    print('текст страницы:', text[:220])
    cks = ctx.cookies('https://www.kimi.com')
    names = sorted({c['name'] for c in cks})
    print('cookies домена kimi.com:', len(cks), '| имена:', names[:14])
    auth = [c for c in cks if c['name'] == 'kimi-auth']
    if auth:
        v = auth[0]['value']
        print('kimi-auth НАЙДЕН | длина', len(v), '| начало', v[:12] + '...', '| httpOnly', auth[0].get('httpOnly'))
    else:
        print('kimi-auth НЕ найден в этой копии профиля')
    ctx.close()