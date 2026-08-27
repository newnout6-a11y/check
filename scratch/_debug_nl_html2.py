# language: python, file: scratch/_debug_nl_html2.py — широкий поиск действия ajax и полей адреса
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
        # все слова рядом с admin-ajax
        for m in re.finditer(r'.{80}admin-ajax\.php.{120}', html):
            print("CTX:", re.sub(r'\s+', ' ', m.group(0)))
            print("---")
        # все input name с postcode/street/house
        for m in re.finditer(r'<input[^>]*(?:postcode|street|house|address)[^>]*>', html, re.I):
            print("INP:", m.group(0)[:200])
        # все data-* атрибуты адресных полей
        for m in re.finditer(r'data-[a-z-]*(?:address|postcode|street|house)[a-z-]*="[^"]*"', html, re.I):
            print("ATTR:", m.group(0)[:160])


if __name__ == "__main__":
    asyncio.run(main())
