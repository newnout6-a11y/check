# language: Python 3.12+, file: link_resolver.py, target: Windows 11, deps: patchright (Chrome)
"""Резолвер платёжных ссылок: открывает линк браузером и достаёт из него сессию.

Зачем браузер, а не HTTP. У рабочей ссылки два обязательных куска: `cs_live_...` в пути и фрагмент
`#fid...` после решётки. Фрагмент живёт ТОЛЬКО на клиенте: браузер не отправляет его на сервер,
поэтому обычный GET его не увидит никогда, а разбор `#fid` нужен для pk (stripe_fid). Плюс Payment
Links (`buy.stripe.com/<slug>`) рождают новую сессию на каждое открытие — это делает JS страницы.
Отсюда правило: платёжный класс самооткрывается только из браузера (devtools/CDP).

Безопасные умолчания (после живого прогона 2026-09-18, где браузер открылся зря):
  * сессионная ссылка (cs+fid уже в адресе) разрешается БЕЗ браузера — он не поднимается вообще;
  * attach по CDP — только когда адрес передан явно ключом --cdp. Порт не сканируется: подключаться
    к чужому запущенному браузеру и ходить в его вкладки нельзя;
  * в подключённом браузере всегда открывается НОВАЯ вкладка, существующие не трогаются;
  * окно по умолчанию скрытое (headless). Видимое — только ключом --show;
  * своё окно закрывается, чужое — никогда.

Живой запуск:
    python link_resolver.py <ссылка> [--cdp http://127.0.0.1:9224] [--show] [--timeout S] [--keep-open]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import shutil
import sys
import time

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

CHROME_PATH = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = shutil.which('chrome') or shutil.which('google-chrome') or 'chromium'

SESSION_RE = re.compile(r'/pay/(cs_(?:live|test)_[A-Za-z0-9]+)')
PROFILE_DIR = pathlib.Path('data/browser_profile')


def split_session(url: str) -> tuple[str, str]:
    """Из адреса — пара (cs, fid). Пустые строки, если куска нет."""
    m = SESSION_RE.search(url or '')
    cs = m.group(1) if m else ''
    frag = (url or '').split('#', 1)[1] if '#' in (url or '') else ''
    fid = frag if frag.startswith('fid') else ''
    return cs, fid


def assemble(cs: str, fid: str) -> str:
    """Собрать рабочую ссылку сессии: путь /c/pay плюс фрагмент."""
    return f'https://checkout.stripe.com/c/pay/{cs}#{fid}' if cs and fid else ''


async def resolve_session(url: str, cdp: str | None = None, timeout: float = 20.0,
                          show: bool = False, keep_open: bool = False) -> dict:
    """Открыть ссылку браузером и вернуть сессию: cs, fid, session_url, чем открывали, сколько ждали.

    Сессионная ссылка возвращается сразу и без браузера; браузер поднимается только для ссылок,
    у которых сессии в адресе нет (платёжный класс).
    """
    started = time.time()
    cs, fid = split_session(url)
    if cs and fid:
        return {'ok': True, 'cs': cs, 'fid': fid, 'session_url': assemble(cs, fid),
                'final_url': url, 'mode': 'без браузера (сессия уже в адресе)',
                'elapsed_s': round(time.time() - started, 2)}

    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        return {'ok': False, 'error': f'patchright недоступен: {e}'}

    async with async_playwright() as pw:
        attached = None
        if cdp:
            try:
                browser = await pw.chromium.connect_over_cdp(cdp)
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                attached = cdp
                mode = f'attach {cdp}'
            except Exception as e:
                return {'ok': False, 'error': f'CDP {cdp} недоступен: {str(e)[:120]}'}
        else:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR.resolve()),
                    channel='chrome' if os.path.exists(CHROME_PATH) else None,
                    headless=not show,
                    args=['--disable-blink-features=AutomationControlled', '--no-first-run'],
                )
            except Exception as e:
                return {'ok': False, 'error': f'браузер не поднялся: {str(e)[:160]}'}
            mode = 'launch chrome' + ('' if show else ' headless')

        page = await ctx.new_page()          # всегда своя вкладка; чужие не трогаем
        final_url = ''
        try:
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=int(timeout * 1000))
            except Exception:
                pass  # редиректы Stripe бросают навигационные исключения — адрес читаем как есть
            deadline = time.time() + timeout
            while time.time() < deadline:
                final_url = page.url
                cs, fid = split_session(final_url)
                if cs and fid:
                    break
                await asyncio.sleep(0.25)
        finally:
            if not keep_open:
                try:
                    await page.close()
                except Exception:
                    pass
                if attached is None:
                    try:
                        await ctx.close()
                    except Exception:
                        pass

    out = {'ok': bool(cs and fid), 'cs': cs, 'fid': fid, 'session_url': assemble(cs, fid),
           'final_url': final_url[:300], 'mode': mode, 'elapsed_s': round(time.time() - started, 2)}
    if not out['ok']:
        out['error'] = ('браузер не получил пару cs+fid: '
                        + ('в адресе нет cs_live/cs_test' if not cs else 'нет разобранного #fid'))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='Резолвер ссылки: сессия из адреса или через браузер')
    ap.add_argument('link')
    ap.add_argument('--cdp', default=None, help='адрес ЖИВОГО Chrome для attach (по умолчанию не подключаемся)')
    ap.add_argument('--show', action='store_true', help='видимое окно (по умолчанию скрытое)')
    ap.add_argument('--timeout', type=float, default=20.0)
    ap.add_argument('--keep-open', action='store_true', help='не закрывать то, что открыли (отладка)')
    a = ap.parse_args()
    res = asyncio.run(resolve_session(a.link, cdp=a.cdp, timeout=a.timeout,
                                      show=a.show, keep_open=a.keep_open))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())