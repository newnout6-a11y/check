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
        types_to_check = [
            "PaymentTermInput",
            "SessionTokenInput",
            "PaymentInput",
            "PaymentMethodInput",
            "DirectPaymentInput",
            "CreditCardPaymentInput",
            "VaultPaymentInput",
            "SubmitForCompletionResult",
            "SubmitForCompletionPayload"
        ]
        for tname in types_to_check:
            r = await s.post(
                "https://epomaker.myshopify.com/checkouts/unstable/graphql",
                json={"query": q, "variables": {"name": tname}},
                headers={"Content-Type": "application/json"}
            )
            data = r.json().get("data", {}).get("__type")
            if data:
                print(f"=== TYPE: {tname} ({data.get('kind')}) ===")
                for f in (data.get("inputFields") or data.get("fields") or []):
                    t = f["type"]
                    t_name = t.get("name") or (t.get("ofType") or {}).get("name")
                    print(f"  {f['name']}: {t_name}")

if __name__ == "__main__":
    asyncio.run(main())
