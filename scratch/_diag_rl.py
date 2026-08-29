import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from curl_cffi.requests import AsyncSession

async def t():
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        for u in ['https://epomaker.myshopify.com', 'https://kith.com', 'https://stevemadden.myshopify.com']:
            try:
                r = await s.get(f'{u}/products.json?limit=5', timeout=10)
                print(u, 'HTTP', r.status_code)
            except Exception as e:
                print(u, 'ERR', type(e).__name__)

asyncio.run(t())
