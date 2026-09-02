import asyncio
import sys
sys.path.insert(0, r"c:\Users\Redmi\Downloads\pusto")
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def test(dom):
    async with AsyncSession(impersonate='chrome120', verify=False) as s:
        url = f'https://{dom}'
        try:
            # 1. empty cart checkout
            r1 = await s.get(f'{url}/checkout/', timeout=8)
            pk1 = gc.extract_pk_live(r1.text or '')
            
            # 2. add item to cart via Store API
            r_cart = await s.get(f'{url}/wp-json/wc/store/v1/cart', timeout=8)
            nonce = r_cart.headers.get('nonce')
            r_prod = await s.get(f'{url}/wp-json/wc/store/v1/products?per_page=3', headers={'Nonce': nonce}, timeout=8)
            prods = r_prod.json()
            pid = prods[0]['id'] if isinstance(prods, list) and prods else None
            if pid:
                nonce = r_prod.headers.get('nonce') or nonce
                r_add = await s.post(f'{url}/wp-json/wc/store/v1/cart/add-item', json={'id': pid, 'quantity': 1}, headers={'Nonce': nonce}, timeout=8)
                # 3. now visit checkout with item in cart!
                r2 = await s.get(f'{url}/checkout/', timeout=8)
                pk2 = gc.extract_pk_live(r2.text or '')
                print(f'{dom}: empty_pk={bool(pk1)} with_cart_pk={bool(pk2)} pk2={pk2[:25] if pk2 else ""}')
            else:
                print(f'{dom}: no prods')
        except Exception as e:
            print(f'{dom}: exc {e}')

async def main():
    for d in ['forageplus.co.uk', 'strictlymedicinalseeds.com', 'thetrendywhippet.co.uk', 'simplerootssoap.com', 'oliveepitome.com', 'bloomscape.com']:
        await test(d)

if __name__ == '__main__':
    asyncio.run(main())
