import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

for meta in soup.find_all("meta"):
    if meta.get("name") == "serialized-graphql":
        data = json.loads(meta.get("content"))
        with open("scratch/serialized_graphql.json", "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
        print("Saved scratch/serialized_graphql.json")
        for k, v in data.items():
            print(f"Operation/Query hash: {k[:40]}... -> keys: {list(v.keys())}")
            if "checkout" in v:
                print("Checkout object keys:", list(v["checkout"].keys()))
                print("Total price:", v["checkout"].get("totalPrice"))
                print("Payment due:", v["checkout"].get("paymentDue"))
                print("Available payment gateways:", v["checkout"].get("availablePaymentGateways"))
