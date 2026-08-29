import asyncio
import json
from curl_cffi.requests import AsyncSession

async def inspect_direct_payment():
    query = """
    query IntrospectDirectPayment {
      direct: __type(name: "CartDirectPaymentMethodInput") {
        name
        inputFields {
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
      submitInput: __type(name: "SubmitForCompletionInput") {
        name
        inputFields {
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
        print("API 2024-07:", json.dumps(r.json(), indent=2))
        
        r2 = await s.post("https://epomaker.myshopify.com/checkouts/unstable/graphql", json={"query": query}, headers={"Content-Type": "application/json"})
        print("Unstable:", json.dumps(r2.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(inspect_direct_payment())
