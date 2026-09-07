# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
import sys

from curl_cffi.requests import AsyncSession
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

DOMAINS = [
    'beehouse.com', 'camamusoap.com', 'coastwoodcommercial.co.nz', 'coffeebeandirect.com',
    'comebackvinyl.com', 'communitycoffee.com', 'donkeylabel.com', 'ecodunia.com',
    'emberycandles.com', 'fallsriversoap.com', 'farmfreshnuts.com', 'gobuyplants.com',
    'greenbottleherbs.com', 'kaffico.com', 'livelyroot.com', 'mealswithmilton.com',
    'mountainmadnesssoap.com', 'oliveoillovers.com', 'plantsbymail.com', 'puritycoffee.com',
    'republicoftea.com', 'rootssea.com', 'rustedacresoaps.com', 'shoptreehaus.com',
    'springhillnursery.com', 'thebeancoffeecompany.com', 'theexoteas.com', 'themaplefarmer.com',
    'thesill.com', 'torquemotors.co.uk', 'torreycandleco.com', 'watersandstone.com',
    'weareknitters.com', 'wildroothoney.com', 'wonena.com'
]

async def check_domain(domain: str, sem: asyncio.Semaphore):
    async with sem:
        url = f"https://{domain}"
        imp = config.pick_impersonate()
        result = {
            "domain": domain,
            "url": url,
            "status": "UNKNOWN",
            "cheapest_cents": None,
            "currency": "USD",
            "cheapest_title": None,
            "err": None
        }
        try:
            async with AsyncSession(impersonate=imp, verify=False, timeout=12) as s:
                r = await s.get(f"{url}/products.json?limit=250")
                if r.status_code == 200:
                    try:
                        data = r.json()
                        prods = data.get("products", [])
                        if not prods:
                            result["status"] = "NO_PRODUCTS"
                        else:
                            candidates = []
                            for p in prods:
                                for v in p.get("variants", []):
                                    if v.get("available") is not False:
                                        try:
                                            p_cents = int(round(float(v.get("price", "999999")) * 100))
                                            if p_cents > 0:
                                                candidates.append((p_cents, p.get("title", ""), v.get("title", "")))
                                        except Exception:
                                            pass
                            if candidates:
                                candidates.sort(key=lambda x: x[0])
                                cheapest = candidates[0]
                                result["cheapest_cents"] = cheapest[0]
                                result["cheapest_title"] = f"{cheapest[1]} ({cheapest[2]})"
                                result["status"] = "OK"
                            else:
                                result["status"] = "NO_AVAILABLE_VARIANTS"
                    except Exception as e:
                        result["status"] = f"JSON_ERR: {e}"
                else:
                    result["status"] = f"HTTP_{r.status_code}"
                
                if result["status"] == "OK":
                    try:
                        rh = await s.get(url, timeout=8)
                        m_cur = re.search(r'"currency_code"\s*:\s*"([A-Z]{3})"', rh.text)
                        if m_cur:
                            result["currency"] = m_cur.group(1)
                        elif "co.nz" in domain:
                            result["currency"] = "NZD"
                        elif "co.uk" in domain or ".uk" in domain:
                            result["currency"] = "GBP"
                    except Exception:
                        pass
        except Exception as e:
            result["status"] = f"ERR_{type(e).__name__}"
            result["err"] = str(e)
        return result

async def main():
    sem = asyncio.Semaphore(10)
    tasks = [check_domain(d, sem) for d in DOMAINS]
    results = await asyncio.gather(*tasks)
    
    ok_count = 0
    over_cap_count = 0
    fail_count = 0
    
    print(f"{'Domain':35} | {'Status':20} | {'Price':10} | {'Currency':5} | Details")
    print("-" * 90)
    for r in sorted(results, key=lambda x: (x['status'] != 'OK', x.get('cheapest_cents') or 999999)):
        c = r['cheapest_cents']
        price_str = f"${c/100:.2f}" if c else "-"
        print(f"{r['domain']:35} | {r['status']:20} | {price_str:10} | {r['currency']:5} | {r['cheapest_title'] or r.get('err') or ''}")
        if r['status'] == 'OK':
            if c and c <= 2000:
                ok_count += 1
            else:
                over_cap_count += 1
        else:
            fail_count += 1
            
    print("-" * 90)
    print(f"Total: {len(results)}, OK (<= $20): {ok_count}, Over Cap (> $20): {over_cap_count}, Failed: {fail_count}")

    with open("scratch/_inspect_35_shopify.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
