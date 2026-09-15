# language: Python 3.12+, file: scratch/_kimi_prof_beforeafter.py
import os, pathlib, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright
tmp = pathlib.Path(tempfile.gettempdir()) / 'kimi_prof'
def names(cks):
    return sorted({c['name'] for c in cks})
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(tmp), channel='chrome', headless=True,
        args=['--no-first-run', '--no-default-browser-check'],
    )
    all_cks = ctx.cookies()
    kimi = [c for c in all_cks if 'kimi' in c.get('domain', '')]
    print('ДО навигации — cookies всего:', len(all_cks), '| kimi:', names(kimi))
    auth = [c for c in kimi if c['name'] == 'kimi-auth']
    print('   kimi-auth до навигации:', 'ЕСТЬ, длина ' + str(len(auth[0]['value'])) if auth else 'НЕТ')
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://www.kimi.com/', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(4000)
    after = [c for c in ctx.cookies() if 'kimi' in c.get('domain', '')]
    print('ПОСЛЕ навигации — kimi cookies:', names(after))
    auth2 = [c for c in after if c['name'] == 'kimi-auth']
    print('   kimi-auth после навигации:', 'ЕСТЬ, длина ' + str(len(auth2[0]['value'])) if auth2 else 'НЕТ (сайт сбросил сессию)')
    print('   UA:', page.evaluate('navigator.userAgent')[:90])
    try:
        r = page.evaluate("async () => { const r = await fetch('/api/user/current', {credentials:'include'}); return {s: r.status, b: (await r.text()).slice(0,120)}; }")
        print('   проверка /api/user/current:', r)
    except Exception as e:
        print('   проверка не удалась:', type(e).__name__)
    ctx.close()