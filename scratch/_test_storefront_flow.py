import asyncio
import json
import uuid
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_storefront_cart_flow(store_url):
    print(f"\n=================== TESTING STOREFRONT CART FLOW ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        api_url = f"{store_url}/api/2024-07/graphql.json"
        
        # 1. Get products via products.json to find cheapest variant
        r_prod = await s.get(f"{store_url}/products.json?limit=50")
        products = r_prod.json().get("products", [])
        variant_id = None
        price_str = "0"
        title = ""
        for p in products:
            for v in p.get("variants", []):
                if v.get("available") and float(v.get("price", "999")) <= 5:
                    variant_id = v["id"]
                    price_str = v.get("price")
                    title = f"{p.get('title')} - {v.get('title')}"
                    break
            if variant_id:
                break
        
        if not variant_id:
            variant_id = products[0]["variants"][0]["id"]
            price_str = products[0]["variants"][0].get("price")
            title = products[0]["title"]
            
        print(f"Product: {title} (ID: {variant_id}, Price: ${price_str})")
        
        # 2. cartCreate
        cart_create_mutation = """
        mutation CartCreate($input: CartInput!) {
          cartCreate(input: $input) {
            cart {
              id
              cost {
                totalAmount {
                  amount
                  currencyCode
                }
              }
              deliveryGroups(first: 1) {
                nodes {
                  id
                  deliveryOptions {
                    handle
                    title
                    cost {
                      amount
                      currencyCode
                    }
                  }
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
        
        create_vars = {
            "input": {
                "lines": [
                    {
                        "merchandiseId": f"gid://shopify/ProductVariant/{variant_id}",
                        "quantity": 1
                    }
                ],
                "buyerIdentity": {
                    "email": "james.smith.testing99@gmail.com",
                    "deliveryAddressPreferences": [
                        {
                            "deliveryAddress": {
                                "firstName": "James",
                                "lastName": "Smith",
                                "address1": "123 Main Street",
                                "city": "New York",
                                "province": "NY",
                                "country": "US",
                                "zip": "10001",
                                "phone": "2125551234"
                            }
                        }
                    ]
                }
            }
        }
        
        r_cart = await s.post(api_url, json={"query": cart_create_mutation, "variables": create_vars}, headers={"Content-Type": "application/json"})
        print("cartCreate Status:", r_cart.status_code)
        cart_data = r_cart.json().get("data", {}).get("cartCreate", {})
        cart = cart_data.get("cart")
        if not cart:
            print("Cart creation failed:", cart_data.get("userErrors"))
            return
        
        cart_id = cart["id"]
        total_amount = cart["cost"]["totalAmount"]["amount"]
        currency = cart["cost"]["totalAmount"]["currencyCode"]
        print(f"Cart ID: {cart_id}, Total: {total_amount} {currency}")
        
        # 3. cartDeliveryAddressesUpdate
        addr_mut = """
        mutation CartDeliveryAddress($cartId: ID!, $addresses: [CartSelectableAddressInput!]!) {
          cartDeliveryAddressesUpdate(cartId: $cartId, addresses: $addresses) {
            cart {
              id
              deliveryGroups(first: 1) {
                nodes {
                  id
                  selectedDeliveryOption {
                    handle
                    title
                  }
                  deliveryOptions {
                    handle
                    title
                    cost {
                      amount
                    }
                  }
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
        addr_vars = {
            "cartId": cart_id,
            "addresses": [
                {
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
                }
            ]
        }
        r_addr = await s.post(api_url, json={"query": addr_mut, "variables": addr_vars}, headers={"Content-Type": "application/json"})
        print("Address update:", r_addr.json().get("data", {}).get("cartDeliveryAddressesUpdate", {}).get("userErrors"))
        
        # 4. cartBillingAddressUpdate
        bill_mut = """
        mutation CartBillingAddress($cartId: ID!, $billingAddress: MailingAddressInput!) {
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
        bill_vars = {
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
        }
        r_bill = await s.post(api_url, json={"query": bill_mut, "variables": bill_vars}, headers={"Content-Type": "application/json"})
        cart_after_bill = r_bill.json().get("data", {}).get("cartBillingAddressUpdate", {}).get("cart")
        if cart_after_bill:
            total_amount = cart_after_bill["cost"]["totalAmount"]["amount"]
            currency = cart_after_bill["cost"]["totalAmount"]["currencyCode"]
        print(f"Final Total Amount: {total_amount} {currency}")
        
        # 5. Tokenize Card on deposit.us.shopifycs.com
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
        print(f"Vaulted session ID: {vault_id}")
        
        # 6. cartPaymentUpdate
        pay_mut = """
        mutation CartPaymentUpdate($cartId: ID!, $payment: CartPaymentInput!) {
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
        pay_vars = {
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
        }
        r_pay = await s.post(api_url, json={"query": pay_mut, "variables": pay_vars}, headers={"Content-Type": "application/json"})
        print("cartPaymentUpdate response:")
        print(json.dumps(r_pay.json(), indent=2))
        
        # 7. cartPrepareForCompletion
        prep_mut = """
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
        r_prep = await s.post(api_url, json={"query": prep_mut, "variables": {"cartId": cart_id}}, headers={"Content-Type": "application/json"})
        print("cartPrepare response:", r_prep.json())
        
        # 8. cartSubmitForCompletion
        submit_mut = """
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
        r_submit = await s.post(api_url, json={"query": submit_mut, "variables": {"cartId": cart_id, "attemptToken": attempt_token}}, headers={"Content-Type": "application/json"})
        print("\n=================== FINAL SUBMIT RESULT ===================")
        print(json.dumps(r_submit.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(test_storefront_cart_flow("https://epomaker.myshopify.com"))
