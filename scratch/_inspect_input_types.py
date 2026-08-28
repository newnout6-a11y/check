import asyncio
import json
from curl_cffi.requests import AsyncSession

async def inspect_input_types(store_url):
    print(f"\n=================== INSPECTING MUTATION INPUTS ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # Introspect types for submitForCompletion and cartPaymentUpdate
        query = """
        query IntrospectTypes {
          checkoutSubmitInput: __type(name: "CheckoutSubmitInput") {
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
          cartPaymentUpdateInput: __type(name: "CartPaymentUpdateInput") {
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
          cartPaymentInput: __type(name: "CartPaymentInput") {
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
          paymentInstrumentInput: __type(name: "PaymentInstrumentInput") {
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
        
        for ep in [f"{store_url}/checkouts/unstable/graphql", f"{store_url}/api/2024-07/graphql.json"]:
            try:
                r = await s.post(ep, json={"query": query}, headers={"Content-Type": "application/json"})
                print(f"\nPOST {ep} -> Status: {r.status_code}")
                data = r.json().get("data", {})
                for k, v in data.items():
                    if v:
                        print(f"--- {k} ({v.get('name')}) ---")
                        for f in v.get("inputFields", []):
                            t = f["type"]
                            t_name = t.get("name") or (t.get("ofType") or {}).get("name")
                            print(f"  {f['name']}: {t_name} ({t.get('kind')})")
            except Exception as e:
                print(f"Error on {ep}: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_input_types("https://epomaker.myshopify.com"))
