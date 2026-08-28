import asyncio
import json
from curl_cffi.requests import AsyncSession

async def introspect_graphql(store_url):
    print(f"\n=================== INTROSPECTING GRAPHQL ON {store_url} ===================")
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        # Introspection query for mutations
        query = """
        query IntrospectMutations {
          __schema {
            mutationType {
              name
              fields {
                name
                description
                args {
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
        }
        """
        
        # Test on unstable/graphql and api/2024-07/graphql.json
        for ep in [f"{store_url}/checkouts/unstable/graphql", f"{store_url}/api/2024-07/graphql.json", f"{store_url}/api/graphql.json"]:
            try:
                r = await s.post(ep, json={"query": query}, headers={"Content-Type": "application/json"})
                print(f"\nPOST {ep} -> Status: {r.status_code}")
                data = r.json()
                if "data" in data and data["data"].get("__schema"):
                    mut_type = data["data"]["__schema"].get("mutationType")
                    if mut_type and mut_type.get("fields"):
                        fields = mut_type["fields"]
                        print(f"Found {len(fields)} available mutations on {ep}:")
                        for f in sorted(fields, key=lambda x: x["name"]):
                            arg_names = [a["name"] for a in f.get("args", [])]
                            print(f"  - {f['name']}({', '.join(arg_names)})")
                    else:
                        print("No mutationType fields found in schema")
                else:
                    print("Errors / No schema:", data.get("errors") or data)
            except Exception as e:
                print(f"Error on {ep}: {e}")

if __name__ == "__main__":
    asyncio.run(introspect_graphql("https://epomaker.myshopify.com"))
