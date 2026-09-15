# language: Python 3.12+, file: scratch/_kimi_state_check.py
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
    ctx = br.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(4000)
    cks = [c for c in ctx.cookies() if 'kimi' in c.get('domain', '')]
    names = sorted({c['name'] for c in cks})
    auth = [c for c in cks if c['name'] == 'kimi-auth']
    print('kimi cookies:', names)
    print('kimi-auth:', ('есть, длина ' + str(len(auth[0]['value']))) if auth else 'НЕТ — сайт сбросил')
    txt = page.inner_text('body').replace(chr(10), ' ')
    print('маркеры входа:', [m for m in ('登录以同步', '登录', '我的 Kimi', '新建项目', '对话') if m in txt])
    print('текст:', txt[:200])
    print('куки в браузере (document.cookie):', page.evaluate("document.cookie.split('; ').map(c=>c.split('=')[0])"))