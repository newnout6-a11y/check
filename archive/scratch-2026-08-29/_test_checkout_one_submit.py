import asyncio
import json
import re
import uuid
from curl_cffi.requests import AsyncSession

TEST_CARD = "4111111111111111|12|2030|123"

async def test_checkout_one_submit(store_url):
    print(f"\n=================== TESTING CHECKOUT ONE GRAPHQL SUBMIT ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # 1. Product
        r_prod = await s.get(f"{store_url}/products.json?limit=50", timeout=10)
        products = r_prod.json().get("products", [])
        variant_id = products[0]["variants"][0]["id"]
        
        # 2. Add to cart
        await s.post(f"{store_url}/cart/add.js", json={"items": [{"id": variant_id, "quantity": 1}]}, timeout=10)
        
        # 3. GET /checkout
        r_chk = await s.get(f"{store_url}/checkout", allow_redirects=True, timeout=15)
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
        shopify_y = get_meta("serialized-shopifyY")
        shopify_s = get_meta("serialized-shopifyS")
        
        print(f"session_token: {str(session_token)[:30]}...")
        print(f"source_token: {source_token}")
        
        # 4. Vault card on deposit.us.shopifycs.com
        cc_num, cc_mm, cc_yy, cc_cvv = TEST_CARD.split("|")
        vault_payload = {
            "credit_card": {
                "number": cc_num,
                "first_name": "James",
                "last_name": "Smith",
                "month": cc_mm,
                "year": cc_yy,
                "verification_value": cc_cvv
            }
        }
        r_vault = await s.post(
            "https://deposit.us.shopifycs.com/sessions",
            json=vault_payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10
        )
        vault_id = r_vault.json().get("id")
        print(f"Vaulted Session ID: {vault_id}")
        
        # 5. Call submitForCompletion mutation
        mutation = """
        mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!) {
          submitForCompletion(input: $input, attemptToken: $attemptToken) {
            __typename
            ... on SubmitSuccess {
              receipt {
                id
                processedAt
              }
              renderContextToken
            }
            ... on SubmitFailed {
              reason
            }
            ... on SubmitRejected {
              reason
            }
            ... on CheckpointDenied {
              reason
            }
            ... on Throttled {
              pollAfter
            }
            ... on SubmittedForCompletion {
              receiptId
              pollAfter
            }
          }
        }
        """
        
        variables = {
            "input": {
                "sessionInput": {
                    "sessionToken": session_token
                },
                "buyerIdentity": {
                    "email": "james.smith.dev99@gmail.com"
                },
                "payment": {
                    "paymentLines": [
                        {
                            "paymentMethod": {
                                "directPaymentMethod": {
                                    "sessionId": vault_id,
                                    "billingAddress": {
                                        "streetAddress": {
                                            "address1": "123 Main St",
                                            "city": "New York",
                                            "countryCode": "US",
                                            "firstName": "James",
                                            "lastName": "Smith",
                                            "phone": "2125551234",
                                            "provinceCode": "NY"
                                        },
                                        "postalCode": {
                                            "postalCode": "10001"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "attemptToken": str(uuid.uuid4())
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
        
        r_mut = await s.post(
            f"{store_url}/checkouts/unstable/graphql",
            json={"query": mutation, "variables": variables},
            headers=headers,
            timeout=15
        )
        print(f"\nGraphQL Submit status: {r_mut.status_code}")
        print("Response JSON:")
        print(json.dumps(r_mut.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_checkout_one_submit("https://epomaker.myshopify.com"))
