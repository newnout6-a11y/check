# language: Python 3.12+, file: scratch/_kimi_fullscreen.py
import json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright
PORT = 9223
ver = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=3).read().decode())
print('браузер на порту', PORT, ':', ver.get('Browser'))
with sync_playwright() as p:
    br = p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
    ctx = br.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('about:blank')
    page.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(3500)
    cdp = ctx.new_cdp_session(page)
    win = cdp.send('Browser.getWindowForTarget')
    print('окно до:', win)
    cdp.send('Browser.setWindowBounds', {'windowId': win['windowId'], 'bounds': {'windowState': 'fullscreen'}})
    page.bring_to_front()
    page.wait_for_timeout(1500)
    after = cdp.send('Browser.getWindowBounds', {'windowId': win['windowId']})
    print('окно после:', after)
    print('страница:', page.url, '|', page.title()[:60])
    print('webdriver:', page.evaluate('navigator.webdriver'))
    txt = page.inner_text('body')
    print('залогинен (нет кнопки входа):', not any(m in txt for m in ('登录以同步', 'Войти для')))