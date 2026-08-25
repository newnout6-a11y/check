# language: Python 3.12+, file: scratch/_probe_walletconfig.py, target: Windows 11
# Variant matrix for merchant-ui-api elements/wallet-config origin handling.
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc

DONOR = "https://www.blackbeltprotein.com.au"
HOST = DONOR.replace("https://", "")


async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r0 = await s.get(f"{DONOR}/my-account/add-payment-method/", timeout=10)
        if not gc.extract_pk_live(r0.text):
            r0 = await s.get(DONOR, timeout=10)
        pk = gc.extract_pk_live(r0.text)
    print(f"[*] pk: {pk[:28]}...")

    variants = [
        ("origin=js.stripe.com", {"Origin": "https://js.stripe.com",
                                  "Referer": f"{DONOR}/my-account/add-payment-method/",
                                  "Accept": "application/json"}),
        ("origin+ref=donor page", {"Origin": DONOR,
                                   "Referer": f"{DONOR}/my-account/add-payment-method/",
                                   "Accept": "application/json"}),
        ("origin=donor bare", {"Origin": DONOR, "Referer": f"{DONOR}/",
                               "Accept": "application/json"}),
        ("no-origin", {"Referer": f"{DONOR}/my-account/add-payment-method/",
                       "Accept": "application/json"}),
    ]
    for name, hdrs in variants:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                r = await s.post("https://merchant-ui-api.stripe.com/elements/wallet-config",
                                 data={"stripe_js_id": str(uuid.uuid4()), "referrer_host": HOST,
                                       "key": pk, "request_surface": "web_split_card_element_popup"},
                                 headers=hdrs, timeout=8)
                body = r.text[:200].replace("\n", " ")
                sk = None
                if r.status_code == 200:
                    try:
                        sk = gc._find_key(r.json(), "link_hcaptcha_site_key")
                    except Exception:
                        pass
                print(f"[{name:22}] HTTP {r.status_code} sitekey={bool(sk)} | {body!r}")
        except Exception as e:
            print(f"[{name:22}] EXC {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
