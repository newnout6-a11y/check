import asyncio
import json
import uuid
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_full_cart_flow(store_url):
    print(f"\n=================== TESTING STOREFRONT CART FULL FLOW ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api_url = f"{store_url}/api/2024-07/graphql.json"
        
        # 1. Product
        r_prod = await s.get(f"{store_url}/products.json?limit=50")
        products = r_prod.json().get("products", [])
        variant_id = None
        for p in products:
            for v in p.get("variants", []):
                if v.get("available") and float(v.get("price", "999")) <= 5:
                    variant_id = v["id"]
                    print(f"Product: {p.get('title')} (${v.get('price')}) [ID: {variant_id}]")
                    break
            if variant_id:
                break
        
        if not variant_id:
            variant_id = products[0]["variants"][0]["id"]
            
        # 2. cartCreate
        q_create = """
        mutation CartCreate($input: CartInput!) {
          cartCreate(input: $input) {
            cart {
              id
              checkoutUrl
              cost {
                totalAmount {
                  amount
                  currencyCode
                }
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        r = await s.post(api_url, json={"query": q_create, "variables": {
            "input": {
                "lines": [{"merchandiseId": f"gid://shopify/ProductVariant/{variant_id}", "quantity": 1}],
                "buyerIdentity": {"email": "james.smith.dev99@gmail.com"}
            }
        }}, headers={"Content-Type": "application/json"})
        
        cart = r.json()["data"]["cartCreate"]["cart"]
        cart_id = cart["id"]
        total_amount = cart["cost"]["totalAmount"]["amount"]
        currency = cart["cost"]["totalAmount"]["currencyCode"]
        print(f"Cart created: {cart_id} | Total: {total_amount} {currency}")
        
        # 3. Delivery address
        q_addr = """
        mutation CartDelivery($cartId: ID!, $addresses: [CartSelectableAddressInput!]!) {
          cartDeliveryAddressesUpdate(cartId: $cartId, addresses: $addresses) {
            cart {
              id
              cost {
                totalAmount {
                  amount
                  currencyCode
                }
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        r = await s.post(api_url, json={"query": q_addr, "variables": {
            "cartId": cart_id,
            "addresses": [{
                "deliveryAddress": {
                    "firstName": "James",
                    "lastName": "Smith",
                    "address1": "123 Main St",
                    "city": "New York",
                    "province": "NY",
                    "country": "US",
                    "zip": "10001",
                    "phone": "2125551234"
                }
            }]
        }}, headers={"Content-Type": "application/json"})
        print("Delivery address response:", r.json())
        
        # 4. Billing address
        q_bill = """
        mutation CartBill($cartId: ID!, $billingAddress: MailingAddressInput!) {
          cartBillingAddressUpdate(cartId: $cartId, billingAddress: $billingAddress) {
            cart {
              id
              cost {
                totalAmount {
                  amount
                  currencyCode
                }
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        r = await s.post(api_url, json={"query": q_bill, "variables": {
            "cartId": cart_id,
            "billingAddress": {
                "firstName": "James",
                "lastName": "Smith",
                "address1": "123 Main St",
                "city": "New York",
                "province": "NY",
                "country": "US",
                "zip": "10001",
                "phone": "2125551234"
            }
        }}, headers={"Content-Type": "application/json"})
        print("Billing address response:", r.json())
        
        # 5. Vault card
        cc_parts = TEST_CARD.split("|")
        vault_payload = {
            "credit_card": {
                "number": cc_parts[0],
                "first_name": "James",
                "last_name": "Smith",
                "month": cc_parts[1],
                "year": cc_parts[2],
                "verification_value": cc_parts[3]
            }
        }
        r_vault = await s.post(
            "https://deposit.us.shopifycs.com/sessions",
            json=vault_payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        vault_id = r_vault.json().get("id")
        print(f"Vaulted Session ID: {vault_id}")
        
        # 6. cartPaymentUpdate
        q_pay = """
        mutation CartPayment($cartId: ID!, $payment: CartPaymentInput!) {
          cartPaymentUpdate(cartId: $cartId, payment: $payment) {
            cart {
              id
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        r_pay = await s.post(api_url, json={"query": q_pay, "variables": {
            "cartId": cart_id,
            "payment": {
                "amount": {
                    "amount": total_amount,
                    "currencyCode": currency
                },
                "directPaymentMethod": {
                    "sessionId": vault_id,
                    "billingAddress": {
                        "firstName": "James",
                        "lastName": "Smith",
                        "address1": "123 Main St",
                        "city": "New York",
                        "province": "NY",
                        "country": "US",
                        "zip": "10001",
                        "phone": "2125551234"
                    }
                }
            }
        }}, headers={"Content-Type": "application/json"})
        print("cartPaymentUpdate response:", json.dumps(r_pay.json(), indent=2))
        
        # 7. cartPrepareForCompletion
        q_prep = """
        mutation CartPrepare($cartId: ID!) {
          cartPrepareForCompletion(cartId: $cartId) {
            result {
              __typename
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        r_prep = await s.post(api_url, json={"query": q_prep, "variables": {"cartId": cart_id}}, headers={"Content-Type": "application/json"})
        print("cartPrepare response:", json.dumps(r_prep.json(), indent=2))
        
        # 8. cartSubmitForCompletion
        q_submit = """
        mutation CartSubmit($cartId: ID!, $attemptToken: String) {
          cartSubmitForCompletion(cartId: $cartId, attemptToken: $attemptToken) {
            result {
              __typename
              ... on SubmitSuccess {
                attemptId
                redirectUrl
              }
              ... on SubmitFailed {
                checkoutUrl
                errors {
                  field
                  message
                  code
                }
              }
              ... on SubmitThrottled {
                pollAfter
              }
              ... on SubmitAlreadyAccepted {
                attemptId
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        attempt_token = str(uuid.uuid4())
        r_submit = await s.post(api_url, json={"query": q_submit, "variables": {"cartId": cart_id, "attemptToken": attempt_token}}, headers={"Content-Type": "application/json"})
        print("\n=================== FINAL SUBMIT RESULT ===================")
        print(json.dumps(r_submit.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(test_full_cart_flow("https://epomaker.myshopify.com"))
