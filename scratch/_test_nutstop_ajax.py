from curl_cffi.requests import Session
import re

s = Session(impersonate="chrome120")
root = "https://www.nutstop.com"
r_shop = s.get(f"{root}/shop/")
print("Shop status:", r_shop.status_code)

headers = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{root}/shop/",
    "Origin": root,
}
r_ajax = s.post(f"{root}/?wc-ajax=add_to_cart", data={"product_id": "9229", "quantity": 1}, headers=headers)
print("Ajax add status:", r_ajax.status_code)
print("Ajax add text:", r_ajax.text[:200])

r_chk = s.get(f"{root}/checkout/", headers={"Referer": f"{root}/shop/"})
print("Checkout status:", r_chk.status_code)
print("Checkout text length:", len(r_chk.text))
m_nonce = re.search(r'name=["\']woocommerce-process-checkout-nonce["\']\s+value=["\']([a-f0-9]+)["\']', r_chk.text)
print("Nonce:", m_nonce.group(1) if m_nonce else None)
