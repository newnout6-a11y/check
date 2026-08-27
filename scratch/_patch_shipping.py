# language: python, file: scratch/_patch_shipping.py — вставка shipping_address в checkout_body
path = "gate_client.py"
src = open(path, encoding="utf-8").read()

anchor = '"customer_note": "", "create_account": False,'
assert src.count(anchor) == 1, f"anchor count = {src.count(anchor)}"

shipping = '''            # physical-goods carts require a valid same-country shipping address
            "shipping_address": {
                "first_name": telem.get("first_name") or ident.get("first_name", "James"),
                "last_name": telem.get("last_name") or ident.get("last_name", "Carter"),
                "company": "",
                "address_1": telem.get("address_1") or ident.get("line1", ""),
                "address_2": "",
                "city": telem.get("city") or ident.get("city", ""),
                "state": ident.get("state", ""),
                "postcode": telem.get("postal_code", ""),
                "country": country,
                "phone": "",
            },
            "customer_note": "", "create_account": False,'''

src = src.replace(anchor, shipping, 1)
open(path, "w", encoding="utf-8").write(src)
print("PATCHED")
