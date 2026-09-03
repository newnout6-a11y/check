import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio, json
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def test():
    async with AsyncSession(impersonate='chrome120') as s:
        api = 'https://kanten.fr/wp-json/wc/store/v1'
        r = await s.get(f'{api}/cart')
        nonce = r.headers.get('nonce')
        # add variation 31791
        r_add = await s.post(f'{api}/cart/add-item', json={'id': 31791, 'quantity': 1}, headers={'Nonce': nonce})
        nonce = r_add.headers.get('nonce') or nonce
        
        # real pk from checkout
        pk = 'pk_live_51Fr5r3K4R0TZzBJXPaf2M3s1ZdQdjvUBPn30uQYGKTH5B8fMgmLBUpAJv2DZC224ndVUhrB82feF6wUulCFptKtu00F9sCZuwS'
        card = gc.parse_card('4559516073479539|01|2029|277')
        telem = gc.stripe_telemetry('https://kanten.fr', pk)
        tok_b = gc.tokenize_body(card, telem, 'https://kanten.fr')
        r_tok = await s.post('https://api.stripe.com/v1/payment_methods', data=tok_b, headers=gc.TOKENIZE_HEADERS)
        pm_id = r_tok.json().get('id')
        print('Tokenized pm_id:', pm_id)
        
        ident = gc.random_identity()
        ident.update(gc.geo_identity_fields('FR'))
        body = {
            'billing_address': {
                'first_name': ident['first_name'], 'last_name': ident['last_name'],
                'company': '', 'address_1': ident['line1'], 'address_2': '',
                'city': ident['city'], 'state': ident['state'], 'postcode': ident['postal_code'],
                'country': 'FR', 'email': ident['email'], 'phone': '0612345678',
            },
            'shipping_address': {
                'first_name': ident['first_name'], 'last_name': ident['last_name'],
                'company': '', 'address_1': ident['line1'], 'address_2': '',
                'city': ident['city'], 'state': ident['state'], 'postcode': ident['postal_code'],
                'country': 'FR', 'phone': '0612345678',
            },
            'payment_method': 'stripe_upm',
            'payment_data': [
                {'key': 'stripe_token', 'value': pm_id},
                {'key': 'payment_method', 'value': 'stripe_upm'},
                {'key': 'wc-stripe-payment-token', 'value': 'new'},
                {'key': 'wc-stripe-is-deferred-intent', 'value': True},
            ],
        }
        r_co = await s.post(f'{api}/checkout', json=body, headers={'Nonce': nonce})
        d = r_co.json()
        print('HTTP Status:', r_co.status_code)
        pr = d.get('payment_result') or {}
        print('Payment result keys:', list(pr.keys()) if isinstance(pr, dict) else pr)
        print('Payment details:', json.dumps(pr.get('payment_details'), indent=2))
        print('Redirect URL:', pr.get('redirect_url'))

if __name__ == '__main__':
    asyncio.run(test())
