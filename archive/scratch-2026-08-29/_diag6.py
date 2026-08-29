# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get("https://magnesiumshop.nl/checkout/", timeout=15)
        html = r.text
        print("status:", r.status_code, "len:", len(html))
        # имена полей формы
        names = re.findall(r'name="([^"]*street[^"]*)"', html, re.I)
        print("street field names:", sorted(set(names)))
        # id полей
        ids = re.findall(r'id="([^"]*street[^"]*)"', html, re.I)
        print("street ids:", sorted(set(ids)))
        # любые address-поля
        addr_names = sorted(set(re.findall(r'name="(billing_[^"]+|shipping_[^"]+)"', html)))
        print("address fields:", addr_names[:25])
        # упоминания street name
        for m in re.finditer(r'.{60}street name.{60}', html, re.I):
            print("ctx:", m.group(0).replace("\n", " ")[:140])

asyncio.run(main())
