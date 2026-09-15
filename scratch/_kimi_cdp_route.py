# language: Python 3.12+, file: scratch/_kimi_cdp_route.py
import json, os, pathlib, shutil, subprocess, sys, tempfile, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
UD = pathlib.Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/User Data'
work = pathlib.Path('C:/ChromeKimi')
if work.exists(): shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)
shutil.copy2(UD / 'Local State', work / 'Local State')
os.system(f'robocopy "{UD / "Profile 8"}" "{work / "Profile 8"}" /E /NFL /NDL /NJH /NJS /NP >NUL')
print('копия профиля:', work, '| файлов:', sum(1 for p in (work/'Profile 8').rglob('*') if p.is_file()))
chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
proc = subprocess.Popen([chrome, f'--user-data-dir={work}', '--profile-directory=Profile 8',
                         '--remote-debugging-port=9223', '--no-first-run', '--no-default-browser-check',
                         '--window-size=1280,900', 'https://www.kimi.com/'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
port_ok = False
for _ in range(20):
    time.sleep(1)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9223/json/version', timeout=2) as r:
            ver = json.loads(r.read().decode())
            print('CDP поднялся на 9223:', ver.get('Browser'), '| UA:', str(ver.get('User-Agent'))[:60])
            port_ok = True
            break
    except Exception:
        continue
if not port_ok:
    print('CDP-порт 9223 не поднялся — Chrome проигнорировал флаг')
    sys.exit(1)
from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
    ctx = br.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print('страница:', page.url)
    page.wait_for_timeout(3500)
    cks = [c for c in ctx.cookies() if 'kimi' in c.get('domain', '')]
    auth = [c for c in cks if c['name'] == 'kimi-auth']
    print('kimi cookies:', sorted({c['name'] for c in cks}))
    print('kimi-auth:', ('ЕСТЬ, длина ' + str(len(auth[0]['value'])) + ' | httpOnly=' + str(auth[0].get('httpOnly'))) if auth else 'НЕТ')
    txt = page.inner_text('body')[:400].replace(chr(10), ' ')
    print('текст:', txt[:200])
    print('webdriver:', page.evaluate('navigator.webdriver'))
    with open('C:/ChromeKimi/_state.json', 'w', encoding='utf-8') as f:
        json.dump({'cookies': {c['name']: c['value'] for c in cks}}, f)
    print('дамп cookies для проверки записан в C:/ChromeKimi/_state.json')