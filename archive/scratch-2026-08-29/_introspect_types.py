import asyncio
import json
from curl_cffi.requests import AsyncSession

async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        q = """
        query Introspect($name: String!) {
          __type(name: $name) {
            name
            kind
            description
            inputFields {
              name
              type {
                name
                kind
                ofType {
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
        for tname in ["NegotiationInput", "PaymentInstrumentInput", "SubmitForCompletionPayload", "SubmitResult"]:
            r = await s.post(
                "https://epomaker.myshopify.com/checkouts/unstable/graphql",
                json={"query": q, "variables": {"name": tname}},
                headers={"Content-Type": "application/json"}
            )
            print(f"=== TYPE: {tname} ===")
            print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
