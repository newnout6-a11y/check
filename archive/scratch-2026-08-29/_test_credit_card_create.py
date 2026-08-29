import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_credit_card_create(store_url):
    print(f"\n=================== TESTING CreditCardCreate on {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Product & Cart
        r_prod = await s.get(f"{store_url}/products.json?limit=10")
        products = r_prod.json().get("products", [])
        variant_id = products[0]["variants"][0]["id"]
        
        await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": variant_id, "quantity": 1}]})
        
        # 2. Checkout GET
        r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True)
        chk_url = r_chk.url
        html = r_chk.text
        
        def get_meta(name):
            m = re.search(rf'name=["\']{name}["\']\s+content=["\']([^"\']+)["\']', html)
            if not m:
                m = re.search(rf'content=["\']([^"\']+)["\']\s+name=["\']{name}["\']', html)
            if m:
                c = m.group(1).replace("&quot;", '"')
                try:
                    return json.loads(c)
                except Exception:
                    return c
            return None
        
        session_token = get_meta("serialized-sessionToken")
        source_token = get_meta("serialized-sourceToken")
        source_type = get_meta("serialized-sourceType")
        shopify_y = get_meta("serialized-shopifyY")
        shopify_s = get_meta("serialized-shopifyS")
        checkout_ident = get_meta("serialized-checkoutSessionIdentifier")
        
        print(f"session_token: {str(session_token)[:25]}...")
        print(f"source_token: {source_token}")
        print(f"checkout_ident: {checkout_ident}")
        
        # 3. Vault Card on deposit.us.shopifycs.com
        cc_parts = TEST_CARD.split("|")
        vault_payload = {
            "credit_card": {
                "number": cc_parts[0],
                "first_name": "John",
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
        print(f"Vaulted ID: {vault_id}")
        
        # 4. Mutation CreditCardCreate
        mutation = """
        mutation CreditCardCreate(
          $billingAddress: AddressInput!,
          $origin: String!,
          $sessionId: ID!,
          $nickname: String,
          $checkoutContext: CheckoutContextInput!
        ) {
          creditCardCreate(
            billingAddress: $billingAddress,
            origin: $origin,
            sessionId: $sessionId,
            nickname: $nickname,
            checkoutContext: $checkoutContext
          ) {
            creditCard {
              id
              brand
              lastDigits
              expiresSoon
              expiryMonth
              expiryYear
              name
              billingAddress {
                address1
                address2
                city
                company
                countryCode
                firstName
                lastName
                phone
                provinceCode
                zip
              }
              __typename
            }
            threeDSecureAuthenticationRequest {
              redirectUrl
              verificationId
              __typename
            }
            userErrors {
              field
              message
              __typename
            }
            __typename
          }
        }
        """
        
        variables = {
            "billingAddress": {
                "firstName": "John",
                "lastName": "Smith",
                "address1": "123 Main St",
                "address2": "",
                "city": "New York",
                "provinceCode": "NY",
                "countryCode": "US",
                "zip": "10001",
                "phone": "2125551234"
            },
            "origin": store_url,
            "sessionId": vault_id,
            "nickname": None,
            "checkoutContext": {
                "checkoutSessionIdentifier": checkout_ident or source_token,
                "source": "CHECKOUT_ONE",
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Checkout-One-Session-Token": session_token or "",
            "X-Shopify-Checkout-Session-Token": session_token or "",
            "X-Shopify-UniqueToken": shopify_y or "",
            "X-Shopify-VisitToken": shopify_s or "",
            "Origin": store_url,
            "Referer": chk_url,
        }
        
        # Try both unstable/graphql and api/graphql.json
        for ep in [f"{store_url}/checkouts/unstable/graphql", f"{store_url}/api/2024-07/graphql.json"]:
            try:
                r_mut = await s.post(ep, json={"query": mutation, "variables": variables}, headers=headers)
                print(f"\nPOST {ep} -> Status: {r_mut.status_code}")
                print("Response JSON:")
                print(json.dumps(r_mut.json(), indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Error on {ep}: {e}")

if __name__ == "__main__":
    asyncio.run(test_credit_card_create("https://epomaker.myshopify.com"))
