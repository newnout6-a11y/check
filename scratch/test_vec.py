import base64
import urllib.parse

tv = "fidnandhYHdWcXxpYCc/J2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc/J2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR/QlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2xwa2FGamlqdyc/JyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic/cXdwYHgl"

# remove fidnandh
payload = tv[len("fidnandh"):]
if payload.endswith('%'):
    payload = payload[:-1]
print("payload len:", len(payload))
# pad base64
pad = payload + "=" * (-len(payload) % 4)
raw = base64.b64decode(pad)
print("raw bytes len:", len(raw))
print("raw as ascii string:")
print(raw.decode('latin1', errors='replace'))
