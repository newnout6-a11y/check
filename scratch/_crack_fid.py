# -*- coding: utf-8 -*-
# Декод fid-фрагмента Stripe Checkout: XOR-перебор + структура
import base64, re, sys
from urllib.parse import unquote, urlsplit
sys.stdout.reconfigure(encoding="utf-8")

URL = "https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc%2FJ2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc%2FJ2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR%2FQlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2pwa2FGamlqdyc%2FJyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl"
frag = unquote(urlsplit(URL).fragment or "")
raw = base64.urlsafe_b64decode((frag + "=" * (-len(frag) % 4)).encode())

# XOR одно-байтовым ключом, ищем pi_secret
for k in range(1, 256):
    dec = bytes(b ^ k for b in raw)
    try:
        txt = dec.decode("utf-8", "ignore")
    except Exception:
        continue
    m = re.search(r"(pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})", txt)
    if m:
        print(f"KEY 0x{k:02x}: SECRET {m.group(1)}")
        print("full:", txt[:300])
        break
else:
    print("однобайтовый XOR не дал secret")
    # смотрю структуру первого байта
    print("raw head bytes:", raw[:24].hex())
