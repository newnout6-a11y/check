# language: Python 3.12+, file: scratch/_kimi_verify.py
import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
    ctx = br.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    seen = []
    page.on('response', lambda r: seen.append((r.status, r.url)) if '/api' in r.url or 'gateway' in r.url else None)
    page.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(6000)
    api = [x for x in seen if '200' in str(x[0])][:6]
    print('=== авторизованные запросы приложения (200) ===')
    for s, u in api: print(f'  {s} {u[:110]}')
    txt = page.inner_text('body')
    print('=== маркеры входа ===')
    print('  есть кнопка «登录/Войти»:', any(m in txt for m in ('登录以同步', 'Войти для')) )
    print('  есть пункт меню «Мой Kimi»:', '我的 Kimi' in txt or 'Мой Kimi' in txt)
    cks = {c['name']: c['value'] for c in ctx.cookies() if 'kimi' in c.get('domain', '')}
    print('  kimi-auth длина:', len(cks.get('kimi-auth', '')))
    page2 = ctx.new_page()
    page2.goto('https://www.kimi.com/user/settings', wait_until='domcontentloaded', timeout=45000)
    page2.wait_for_timeout(4000)
    t2 = page2.inner_text('body')[:220].replace(chr(10), ' ')
    print('  страница настроек:', page2.url[:60], '|', t2[:150])
    page2.close()
    print('=== проверка куки в ЧИСТОМ контексте (без профиля) ===')
    clean = br.new_context()
    clean.add_cookies([
        {'name': 'kimi-auth', 'value': cks['kimi-auth'], 'domain': 'www.kimi.com', 'path': '/', 'httpOnly': True, 'secure': True},
        {'name': 'theme', 'value': cks.get('theme', 'light'), 'domain': 'www.kimi.com', 'path': '/', 'secure': True},
    ])
    pg = clean.new_page()
    pg.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    pg.wait_for_timeout(5000)
    t3 = pg.inner_text('body')
    print('  чистый контекст: «我的 Kimi» есть:', '我的 Kimi' in t3, '| «登录以同步» есть:', '登录以同步' in t3)
    clean.close()