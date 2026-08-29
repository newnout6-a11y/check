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
            possibleTypes {
              name
            }
          }
        }
        """
        types = [
            "SubmitSuccess",
            "SubmitFailed",
            "SubmitRejected",
            "CheckpointDenied",
            "SubmittedForCompletion",
            "Receipt",
            "OrderReceipt",
            "StandardReceipt"
        ]
        for t in types:
            r = await s.post(
                "https://epomaker.myshopify.com/checkouts/unstable/graphql",
                json={"query": q, "variables": {"name": t}},
                headers={"Content-Type": "application/json"}
            )
            data = r.json().get("data", {}).get("__type")
            print(f"=== {t} ===")
            if data:
                if data.get("possibleTypes"):
                    print("  Possible types:", [p["name"] for p in data["possibleTypes"]])
                for f in data.get("fields") or []:
                    t_name = f["type"].get("name") or (f["type"].get("ofType") or {}).get("name")
                    print(f"  {f['name']}: {t_name}")

if __name__ == "__main__":
    asyncio.run(main())
