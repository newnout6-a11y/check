# -*- coding: utf-8 -*-
import asyncio, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession

JS_URL = "https://js.stripe.com/v3/fingerprinted/js/stripe-a5ce45299cbf7c4afe3c9a04fa58d474.js?stripeCheckoutInitialized=true"

async def main():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(JS_URL, timeout=30)
        js = r.text
        print(f"бандл: {len(js)} символов, {r.status_code}")
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        open(os.path.join(base, "scratch", "_checkout_bundle.js"), "w", encoding="utf-8").write(js)
        eps = set(re.findall(r'(/[a-z0-9/_.-]{4,60})', js))
        interesting = [e for e in eps if any(k in e for k in
                       ("session", "checkout", "elements", "pay", "confirm", "init"))]
        print("эндпоинты:")
        for e in sorted(interesting)[:30]:
            print('  ', e)
        for m in re.finditer(r".{50}atob.{90}", js):
            print('ATOB:', m.group(0)[:150])

asyncio.run(main())