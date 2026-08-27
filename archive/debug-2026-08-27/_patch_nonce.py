# language: python, file: scratch/_patch_nonce.py — обновление nonce из ответов Store API
path = "gate_client.py"
src = open(path, encoding="utf-8").read()

# хелпер сразу после открытия try в store_api_confirm
anchor = '''        r_cart = await s.get(f"{api}/cart", timeout=10)
        nonce = r_cart.headers.get("nonce", "")
        if not nonce:
            return {"status": "ERROR", "detail": "Store API: no Nonce header",
                    "amount_cents": 0, "currency": ""}'''
assert src.count(anchor) == 1, f"anchor count = {src.count(anchor)}"

replacement = '''        def _take_nonce(resp) -> None:
            """Store API nonce одноразовый на мутацию — каждый ответ несёт свежий."""
            nn = resp.headers.get("nonce") or resp.headers.get("Nonce")
            if nn:
                nonlocal_nonce[0] = nn

        nonlocal_nonce = [r_cart.headers.get("nonce", "")]
        nonce = nonlocal_nonce[0]
        _take_nonce(r_cart)
        if not nonce:
            return {"status": "ERROR", "detail": "Store API: no Nonce header",
                    "amount_cents": 0, "currency": ""}'''
src = src.replace(anchor, replacement, 1)

# все хождения с nonce -> берём актуальный и обновляем после ответа
src = src.replace(
    '''            r_prod = await s.get(f"{api}/products", params={"per_page": 30},
                              headers={"Nonce": nonce}, timeout=10)''',
    '''            r_prod = await s.get(f"{api}/products", params={"per_page": 30},
                              headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
            _take_nonce(r_prod)''', 1)

src = src.replace(
    '''            r_add = await s.post(f"{api}/cart/add-item",
                                  params={"id": cand_p["id"], "quantity": "1"},
                                  headers={"Nonce": nonce}, timeout=10)''',
    '''            r_add = await s.post(f"{api}/cart/add-item",
                                  params={"id": cand_p["id"], "quantity": "1"},
                                  headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_add)''', 1)

src = src.replace(
    '''                r_car2 = await s.get(f"{api}/cart", headers={"Nonce": nonce}, timeout=10)''',
    '''                r_car2 = await s.get(f"{api}/cart",
                                     headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_car2)''', 1)

src = src.replace(
    '''                    await s.post(f"{api}/cart/update-customer",
                             json={
                                 "shipping_address": {
                                     "first_name": ident_pre["first_name"],
                                     "last_name": ident_pre["last_name"],
                                     "company": "",
                                     "address_1": ident_pre.get("line1", ""),
                                     "address_2": "",
                                     "city": ident_pre.get("city", ""),
                                     "state": ident_pre.get("state", ""),
                                     "postcode": ident_pre.get("postal_code", ""),
                                     "country": country,
                                     "phone": "",
                                 },
                             },
                             headers={"Nonce": nonce}, timeout=10)''',
    '''                    r_uc = await s.post(f"{api}/cart/update-customer",
                             json={
                                 "shipping_address": {
                                     "first_name": ident_pre["first_name"],
                                     "last_name": ident_pre["last_name"],
                                     "company": "",
                                     "address_1": ident_pre.get("line1", ""),
                                     "address_2": "",
                                     "city": ident_pre.get("city", ""),
                                     "state": ident_pre.get("state", ""),
                                     "postcode": ident_pre.get("postal_code", ""),
                                     "country": country,
                                     "phone": "",
                                 },
                             },
                             headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                    _take_nonce(r_uc)''', 1)

src = src.replace(
    '''                await s.post(f"{api}/cart/select-shipping-rate",
                             json={"rate_id": rate_id},
                             headers={"Nonce": nonce}, timeout=10)''',
    '''                r_sr = await s.post(f"{api}/cart/select-shipping-rate",
                             json={"rate_id": rate_id},
                             headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_sr)''', 1)

src = src.replace(
    '''            r_draft = await s.get(f"{api}/checkout", headers={"Nonce": nonce}, timeout=10)''',
    '''            r_draft = await s.get(f"{api}/checkout",
                                   headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
            _take_nonce(r_draft)''', 1)

src = src.replace(
    '''            r_co = await s.post(f"{api}/checkout", json=checkout_body,
                                headers={"Nonce": nonce}, timeout=20)''',
    '''            r_co = await s.post(f"{api}/checkout", json=checkout_body,
                                headers={"Nonce": nonlocal_nonce[0]}, timeout=20)
            _take_nonce(r_co)''', 1)

open(path, "w", encoding="utf-8").write(src)
print("PATCHED")
