import base64
import urllib.parse
import json

tv = "fidnandhYHdWcXxpYCc/J2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc/J2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR/QlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2xwa2FGamlqdyc/JyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic/cXdwYHgl"

# Let's test different cutoffs of tv:
for cut in range(0, 15):
    prefix = tv[:cut]
    payload = tv[cut:].rstrip('%')
    try:
        pad = payload + "=" * (-len(payload) % 4)
        raw = base64.b64decode(pad)
        xored = "".join(chr(5 ^ b) for b in raw)
        print(f"Cut {cut:2d} (prefix '{prefix}'): {xored[:60]}...{xored[-20:]}")
        if xored.strip().startswith("{") and xored.strip().endswith("}"):
            print("  ===> PERFECT JSON MATCH! <===")
            d = json.loads(xored.strip())
            print(json.dumps(d, indent=2))
    except Exception as e:
        pass
