# language: Python 3.12+, file: tests/test_stripe_fid.py, target: Windows 11
import json
import pytest
from stripe_fid import decode_fragment, encode_fragment

TEST_FID = (
    "fidnandhYHdWcXxpYCc/J2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1Brb"
    "HRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc/J2Zqa3F3amknKSdkdW"
    "xOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR/QlFOQkNuNG9AZk"
    "NVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3"
    "ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2xwa2FGamlqdyc/JyZjY2NjY2MnKSd"
    "pZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic/cXdwYHgl"
)

TEST_URL = f"https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#{TEST_FID}"


def test_decode_full_url():
    res = decode_fragment(TEST_URL)
    assert res.get("apiKey") == "pk_live_51MxsTWJtv8NUoFyIcuCCBgzkB0qzGTKGFk1jEcFPjQ08uoK243j6FHglNyncdeEVbzNjq0TrN5k78QFJQvPJpfkV00c2sZ7C3n"
    assert res.get("checkoutSessionId") == "cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz"
    assert res.get("borderStyle") == "default"
    assert res.get("locale") == "en"
    assert res.get("guacamoleVariant") == "control"
    assert res.get("enablePlaceholders") is True
    assert res.get("client_secret") is not None


def test_decode_raw_fid():
    res = decode_fragment(TEST_FID)
    assert res.get("apiKey") == "pk_live_51MxsTWJtv8NUoFyIcuCCBgzkB0qzGTKGFk1jEcFPjQ08uoK243j6FHglNyncdeEVbzNjq0TrN5k78QFJQvPJpfkV00c2sZ7C3n"
    assert res.get("layoutType") == "multi_item"


def test_roundtrip_encode_decode():
    sample = {
        "apiKey": "pk_live_test123",
        "locale": "ru",
        "layoutType": "accordion",
        "enablePlaceholders": False
    }
    encoded = encode_fragment(sample)
    decoded = decode_fragment(encoded)
    assert decoded == sample


def test_empty_or_invalid():
    assert decode_fragment("") == {}
    assert decode_fragment(None) == {}
