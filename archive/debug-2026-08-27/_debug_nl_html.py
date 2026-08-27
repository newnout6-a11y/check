# language: python, file: scratch/_debug_nl_html.py — ищем wcnlpc эндпоинты в чекауте
import asyncio
import re
import sys

from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


async def main():
    root = "https://magnesiumshop.nl"
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(f"{root}/checkout/", timeout=15)
        html = r.text
        print("len:", len(html))
        # ищем ajax-URL и поля postcode-плагина
        for pat in (r'admin-ajax\.php[^"\']*', r'action["\']?\s*[:=]\s*["\'](\w+)',
                    r'wcnlpc\w*', r'postcode[_-]?check\w*', r'housenumber\w*',
                    r'data-\w*street\w*', r'validate[_-]?\w*'):
            hits = sorted(set(re.findall(pat, html, re.I)))[:12]
            if hits:
                print(f"\n/{pat}/ ->")
                for h in hits:
                    print("   ", h[:120])
        # фрагмент формы адреса
        m = re.search(r'<form[^>]*checkout[^>]*>(.{0,3000})', html, re.S | re.I)
        if m:
            print("\nform head:", re.sub(r'\s+', ' ', m.group(1))[:1000])


if __name__ == "__main__":
    asyncio.run(main())
