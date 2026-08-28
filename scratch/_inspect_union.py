import asyncio
import json
from curl_cffi.requests import AsyncSession

async def inspect_union_types():
    query = """
    query IntrospectUnion {
      submitResult: __type(name: "CartSubmitForCompletionResult") {
        name
        possibleTypes {
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
    }
    """
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.post("https://epomaker.myshopify.com/api/2024-07/graphql.json", json={"query": query}, headers={"Content-Type": "application/json"})
        print("Union Types:", json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(inspect_union_types())
