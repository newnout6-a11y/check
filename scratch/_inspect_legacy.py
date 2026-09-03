import sys, os
sys.path.insert(0, os.path.abspath("."))
import re
from curl_cffi.requests import Session
import gate_client as gc

candidates = ["https://nutstop.com", "https://oceanwp.org", "https://skeivteori.no", "https://essexmonastery.com"]

for url in candidates:
    print(f"\n[*] Checking {url}...")
    s = Session(impersonate="chrome120")
    try:
        r = s.get(url + "/shop/", timeout=10)
        print("Shop status:", r.status_code)
        pids = re.findall(r'data-product_id=["\'](\d+)["\']', r.text)
        if not pids:
            pids = re.findall(r'add-to-cart=(\d+)', r.text)
        print("Product IDs:", pids[:5])
        pk = gc.extract_pk_live(r.text)
        print("PK on shop:", pk)
        if pids:
            pid = pids[0]
            r_add = s.post(f"{url}/?wc-ajax=add_to_cart", data={"product_id": pid, "quantity": 1}, timeout=10)
            print("Add-to-cart status:", r_add.status_code)
            r_chk = s.get(f"{url}/checkout/", timeout=10)
            nonce = re.findall(r'name=["\']woocommerce-process-checkout-nonce["\']\s+value=["\']([a-f0-9]+)["\']', r_chk.text)
            pk_chk = gc.extract_pk_live(r_chk.text)
            print(f"Checkout status: {r_chk.status_code}, Nonce: {nonce}, PK: {pk_chk}")
    except Exception as e:
        print("Error:", e)
