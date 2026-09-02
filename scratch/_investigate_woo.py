import asyncio
import json
import re
import sys
sys.path.insert(0, r"c:\Users\Redmi\Downloads\pusto")
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
from curl_cffi.requests import AsyncSession
import config
import gate_client as gc

POOL_PATH = "data/scout_pool.json"

async def check_domain(dom):
    url = f"https://{dom}"
    print(f"\n=================== {dom} ===================")
    imp = config.pick_impersonate()
    async with AsyncSession(impersonate=imp, verify=False) as s:
        # 1. Check /checkout/
        try:
            r_co = await s.get(f"{url}/checkout/", timeout=10)
            text = r_co.text or ""
            pk = gc.extract_pk_live(text)
            pks = re.findall(r"pk_(?:live|test)_[0-9a-zA-Z]{20,}", text)
            print(f"  /checkout/: status={r_co.status_code}, len={len(text)}, PKs={pks}")
            
            # Check other gateways
            braintree = "braintree" in text.lower() or "authorization" in text.lower()
            authorizenet = "authorizenet" in text.lower() or "accept.js" in text.lower()
            square = "square" in text.lower() or "sq0idp" in text
            mollie = "mollie" in text.lower()
            cybersource = "cybersource" in text.lower() or "flex.microform" in text
            adyen = "adyen" in text.lower()
            
            gateways = []
            if pks: gateways.append(f"Stripe({pks[0][:15]}...)")
            if braintree: gateways.append("Braintree")
            if authorizenet: gateways.append("Authorize.Net")
            if square: gateways.append("Square")
            if mollie: gateways.append("Mollie")
            if cybersource: gateways.append("CyberSource")
            if adyen: gateways.append("Adyen")
            print(f"  Detected Gateways on /checkout/: {gateways}")

            # Check script tags
            scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', text)
            pay_scripts = [sc for sc in scripts if any(k in sc.lower() for k in ["stripe", "braintree", "mollie", "square", "authoriz", "payment", "checkout"])]
            print(f"  Payment Scripts ({len(pay_scripts)}): {pay_scripts[:5]}")
        except Exception as e:
            print(f"  /checkout/ EXC: {e}")

        # 2. Check Store API /cart
        try:
            r_cart = await s.get(f"{url}/wp-json/wc/store/v1/cart", timeout=8)
            if r_cart.status_code == 200:
                cdata = r_cart.json()
                methods = cdata.get("payment_methods", [])
                p_reqs = cdata.get("payment_requirements", [])
                print(f"  Store API Cart: methods={methods}, requirements={p_reqs}")
            else:
                print(f"  Store API Cart HTTP {r_cart.status_code}")
        except Exception as e:
            print(f"  Store API Cart EXC: {e}")

async def main():
    pool = json.load(open(POOL_PATH, "r", encoding="utf-8"))
    no_pk = [e for e in pool if "storegate" in e.get("routes", []) and not e.get("stripe_pk")]
    print(f"Total StoreGate candidates without PK: {len(no_pk)}")
    for e in no_pk[:8]:
        await check_domain(e["domain"])

if __name__ == "__main__":
    asyncio.run(main())
