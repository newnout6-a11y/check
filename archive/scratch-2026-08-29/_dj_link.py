# -*- coding: utf-8 -*-
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import stripe_fid

URL = 'https://checkout.stripe.com/c/pay/cs_live_a17uc8AaPsS4H0K9R9tiEa0FI6CQR0a2MrbJ8kpTiufvs5QQvQcmMsLF3E#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPyd3cCcpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9xd3BgKSdicGRmZGhqaWBTZHdsZGtxJz8nZmprcXdqaScpJ2R1bE5gfCc%2FJ3VuWmlsc2BaMDRLVmE0ZE40VFxnbUJiQXV1dEYxRjM1RENEc3U8YVJEMUNuSXZcPUp8bzN1fE4zcjFfR01tTX9QbWdENVA2STxAZFY9cndNR2pzS2tUUlNkQzdEbzxHbEM1NVVSdXJSfXx1JyknY3dqaFZgd3Ngdyc%2FcXdwYCknZ2RmbmJ3anBrYUZqaWp3Jz8nJmNjY2NjYycpJ2lkfGpwcVF8dWAnPyd2bGtiaWBabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl'

async def main():
    d = stripe_fid.decode_fragment(URL)
    print('cs:', d.get('checkoutSessionId', '?')[:40])
    print('pk:', str(d.get('apiKey'))[:30])
    async with AsyncSession(impersonate='chrome131', verify=False) as s:
        r = await s.get(f"https://api.stripe.com/v1/payment_pages/{d['checkoutSessionId']}",
                        params={'key': d['apiKey']},
                        headers={'Origin': 'https://js.stripe.com', 'Referer': 'https://js.stripe.com/', 'Accept': 'application/json'},
                        timeout=12)
        data = r.json()
        print('HTTP:', r.status_code)
        for k in ('status', 'payment_status', 'mode', 'submit_type', 'livemode', 'is_sandbox_merchant', 'amount_total'):
            print(f'  {k}:', data.get(k))
        print('  PI:', (data.get('payment_intent') or {}).get('status'))
        print('  setup_intent:', (data.get('setup_intent') or {}).get('status'))
        ts = data.get('total_summary') or {}
        print('  total:', str(ts)[:200])

asyncio.run(main())