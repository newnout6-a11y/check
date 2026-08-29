import asyncio
import json
from curl_cffi.requests import AsyncSession

async def debug_cart_create():
    api_url = "https://epomaker.myshopify.com/api/2024-07/graphql.json"
    variant_id = 49239675633972
    cart_create_mutation = """
    mutation CartCreate($input: CartInput!) {
      cartCreate(input: $input) {
        cart {
          id
        }
        userErrors {
          field
          message
          code
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
            ]
        }
    }
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.post(api_url, json={"query": cart_create_mutation, "variables": create_vars}, headers={"Content-Type": "application/json"})
        print("Status:", r.status_code)
        print("Response:", json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(debug_cart_create())
