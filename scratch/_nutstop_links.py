from curl_cffi.requests import Session
import re

s = Session(impersonate='chrome120')
url = 'https://www.nutstop.com/product/black-beans/'
r_prod = s.get(url)
print("1. Product get:", r_prod.status_code)

# Добавляем в корзину через POST на страницу товара
r_add = s.post(url, data={'add-to-cart': '9229', 'quantity': 1}, timeout=12)
print("2. Add to cart status:", r_add.status_code)

# Заходим на чекаут
r_chk = s.get('https://www.nutstop.com/checkout/', timeout=12)
print("3. Checkout status:", r_chk.status_code)

# Ищем nonce чекаута
m_nonce = re.search(r'name=["\']woocommerce-process-checkout-nonce["\']\s+value=["\']([a-f0-9]+)["\']', r_chk.text)
if not m_nonce:
    m_nonce = re.search(r'id=["\']woocommerce-process-checkout-nonce["\']\s+value=["\']([a-f0-9]+)["\']', r_chk.text)
nonce = m_nonce.group(1) if m_nonce else None
print("4. Checkout nonce:", nonce)

# Ищем pk_live
import sys, os
sys.path.insert(0, os.path.abspath("."))
import gate_client as gc
pk = gc.extract_pk_live(r_chk.text)
print("5. PK live on checkout:", pk)

# Ищем доступные payment methods
methods = re.findall(r'name=["\']payment_method["\']\s+value=["\']([^"\']+)["\']', r_chk.text)
print("6. Payment methods on checkout:", set(methods))
