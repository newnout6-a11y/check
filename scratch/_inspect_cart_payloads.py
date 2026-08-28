import asyncio
import json
from curl_cffi.requests import AsyncSession

async def inspect_cart_payloads():
    query = """
    query IntrospectCartPayloads {
      cartSubmit: __type(name: "CartSubmitForCompletionPayload") {
        name
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
      cartPayment: __type(name: "CartPaymentUpdatePayload") {
        name
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
      cartPrepare: __type(name: "CartPrepareForCompletionPayload") {
        name
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
    """
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.post("https://epomaker.myshopify.com/api/2024-07/graphql.json", json={"query": query}, headers={"Content-Type": "application/json"})
        print("Cart Payloads:", json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(inspect_cart_payloads())
