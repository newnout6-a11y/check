# language: Python 3.12+, file: scratch/_probe_stripe_endpoints.py, target: Windows 11
# Empirical probe: which m.stripe.com/6 request shape actually issues __stripe_mid/sid,
# and what elements/wallet-config really returns. Read-only diagnostics.
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc

DONOR = "https://www.blackbeltprotein.com.au"
PK = ""  # filled from donor page below


async def get_pk():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(f"{DONOR}/my-account/add-payment-method/", timeout=10)
        # not logged in: pk still present in checkout scripts? fall back to reg page
        if not gc.extract_pk_live(r.text):
            r = await s.get(DONOR, timeout=10)
        return gc.extract_pk_live(r.text)


async def main():
    pk = await get_pk()
    print(f"[*] pk_live from donor: {pk[:28]}..." if pk else "[!] no pk found")

    shapes = [
        ("GET bare", lambda s: s.get("https://m.stripe.com/6",
                                     headers={"Origin": DONOR, "Referer": f"{DONOR}/", "Accept": "*/*"}, timeout=8)),
        ("GET v3-heartbeat", lambda s: s.get("https://m.stripe.com/6/v3",
                                             headers={"Origin": DONOR, "Referer": f"{DONOR}/"}, timeout=8)),
        ("POST empty-form", lambda s: s.post("https://m.stripe.com/6", data={},
                                             headers={"Origin": "https://js.stripe.com",
                                                      "Referer": "https://js.stripe.com/", "Accept": "*/*"}, timeout=8)),
        ("POST beacon-json", lambda s: s.post("https://m.stripe.com/6",
                                              json={"v": "t", "url": DONOR, "lsid": str(uuid.uuid4()),
                                                    "guid": str(uuid.uuid4()), "muid": str(uuid.uuid4())},
                                              headers={"Origin": "https://js.stripe.com",
                                                       "Referer": "https://js.stripe.com/"}, timeout=8)),
    ]
    for name, fn in shapes:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                r = await fn(s)
                try:
                    sc = r.headers.get_list("set-cookie")
                except Exception:
                    sc = []
                jar = s.cookies.get_dict()
                mid = next((v.split(";")[0] for k, v in jar.items() if k == "__stripe_mid"), "")
                sid = next((v.split(";")[0] for k, v in jar.items() if k == "__stripe_sid"), "")
                parsed = gc.parse_stripe_cookies(sc)
                body_head = (r.text or "")[:120].replace("\n", " ")
                print(f"[{name:18}] HTTP {r.status_code} | set-cookie:{len(sc)} "
                      f"| hdr-mid:{bool(parsed['mid'])} jar-mid:{bool(mid)} jar-sid:{bool(sid)} | body: {body_head!r}")
        except Exception as e:
            print(f"[{name:18}] EXC {type(e).__name__}: {e}")

    if pk:
        print("-" * 70)
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            host = DONOR.replace("https://", "")
            r = await s.post("https://merchant-ui-api.stripe.com/elements/wallet-config",
                             data={"stripe_js_id": str(uuid.uuid4()), "referrer_host": host,
                                   "key": pk, "request_surface": "web_split_card_element_popup"},
                             headers={"Origin": DONOR, "Referer": "https://js.stripe.com/",
                                      "Accept": "application/json"}, timeout=8)
            print(f"[wallet-config] HTTP {r.status_code}")
            txt = r.text[:400]
            print(f"  body: {txt!r}")
            sk = gc._find_key(r.json() if r.status_code == 200 else {}, "link_hcaptcha_site_key")
            print(f"  link_hcaptcha_site_key: {sk}")
            if sk:
                r2 = await s.post("https://api.hcaptcha.com/checksiteconfig",
                                  params={"v": gc.STRIPE_JS_BUILD, "sitekey": sk,
                                          "host": "b.stripecdn.com", "sc": "1", "swa": "1"},
                                  headers={"Origin": "https://b.stripecdn.com",
                                           "Referer": "https://b.stripecdn.com/",
                                           "Accept": "application/json"}, timeout=8)
                print(f"[checksiteconfig] HTTP {r2.status_code} body: {r2.text[:300]!r}")


if __name__ == "__main__":
    asyncio.run(main())
