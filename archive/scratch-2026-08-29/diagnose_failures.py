# language: Python 3.12+, file: scratch/diagnose_failures.py, target: Windows 11, deps: curl_cffi
# Пошаговая диагностика: до какой стадии домен дошёл и почему отвалился.
# Логика регистрации/скрапа — из общего движка gate_client.
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень проекта при любом cwd

from curl_cffi.requests import AsyncSession

import gate_client as gc


async def diagnose_domain(domain: str):
    base = f"https://{domain}"
    reg_url = f"{base}/my-account/"
    diag = {"domain": domain, "step": "init", "reason": ""}

    try:
        async with AsyncSession(impersonate="chrome131", verify=False) as s:
            # 1. GET
            r_get = await s.get(reg_url, timeout=10)
            if r_get.status_code != 200:
                diag.update(step="GET /my-account/", reason=f"HTTP {r_get.status_code}")
                return diag
            html = r_get.text

            if gc.is_cloudflare_challenge(html):
                diag.update(step="GET /my-account/", reason="Cloudflare challenge page")
                return diag

            reg_nonce = gc.extract_reg_nonce(html)
            if not reg_nonce:
                diag.update(step="GET /my-account/", reason="No register nonce in HTML")
                return diag

            # 2. POST registration
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
                diag.update(step="POST /my-account/ (Register)",
                            reason="No login cookie (honeypot / bot challenge)")
                return diag

            # 3. GET add-payment-method
            r_pm = await s.get(f"{base}/my-account/add-payment-method/", timeout=10)
            pm_html = r_pm.text

            if "pk_test_" in pm_html and "pk_live_" not in pm_html:
                diag.update(step="GET /add-payment-method/", reason="Test mode only (pk_test_)")
                return diag

            scraped = gc.scrape_gate(pm_html)
            pk, upe = scraped["pk"], scraped["upe_nonce"]
            legacy = scraped["legacy_nonce"]

            if not pk:
                diag.update(step="GET /add-payment-method/",
                            reason="No pk_live found (saved_cards disabled or non-Stripe)")
                return diag
            if not upe and not legacy:
                diag.update(step="GET /add-payment-method/",
                            reason=f"pk_live found ({pk[:16]}...) but no SetupIntent nonces")
                return diag

            diag.update(step="Stage 4 (Confirm)",
                        reason=f"Ready for confirm | PK={pk[:16]}... UPE={bool(upe)}")
            return diag
    except Exception as e:
        diag.update(step="Network/Exception", reason=str(e)[:100])
        return diag


async def main():
    with open("data/harvested_domains.txt", encoding="utf-8") as f:
        domains = [l.strip() for l in f if l.strip()]

    sem = asyncio.Semaphore(20)

    async def bound_diag(d):
        async with sem:
            return await diagnose_domain(d)

    results = await asyncio.gather(*[bound_diag(d) for d in domains[:40]])
    print(json.dumps(results[:15], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
