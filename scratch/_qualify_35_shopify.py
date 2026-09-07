# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import gate_client as gc
import shopify_gate as sg
from curl_cffi.requests import AsyncSession

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

async def process_domain(d: str, sem: asyncio.Semaphore):
    async with sem:
        url = f"https://{d}"
        res = {
            "url": url,
            "domain": d,
            "cheapest_cents": None,
            "currency": "USD",
            "verified": False,
            "over_cap": False,
            "status": "INIT",
            "title": "",
            "last_live_check": "2026-09-07",
            "last_live_verdict": "ERROR"
        }
        
        # 1. Fetch products
        try:
            async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, timeout=12) as s:
                p = await sg.get_shopify_cheapest_product(s, url, max_price_cents=100000) # up to $1000 to find actual price
                if not p:
                    # try www.
                    url_www = f"https://www.{d}"
                    p = await sg.get_shopify_cheapest_product(s, url_www, max_price_cents=100000)
                    if p:
                        url = url_www
                        res["url"] = url
                
                if not p:
                    res["status"] = "NO_PRODUCTS"
                    res["last_live_verdict"] = "NO_PRODUCTS"
                    return res
                
                res["cheapest_cents"] = p["price_cents"]
                res["title"] = p.get("product_title", "")
                
                # Check currency
                try:
                    rh = await s.get(url, timeout=8)
                    m_cur = re.search(r'"currency_code"\s*:\s*"([A-Z]{3})"', rh.text)
                    if m_cur:
                        res["currency"] = m_cur.group(1)
                    elif "co.nz" in d:
                        res["currency"] = "NZD"
                    elif "co.uk" in d or ".uk" in d:
                        res["currency"] = "GBP"
                except Exception:
                    pass
                
                if res["cheapest_cents"] > 2000:
                    res["over_cap"] = True
                    res["verified"] = True
                    res["status"] = "OVER_CAP"
                    res["last_live_verdict"] = f"OVER_CAP_{res['cheapest_cents']}c"
                    return res
                
                # 2. Under cap <= 2000c -> probe with test card
                probe = gc.gen_probe_card()
                card_str = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
                try:
                    r_chk = await sg.check_target(url, card_str, max_price_cents=res["cheapest_cents"])
                    st = r_chk.get("status", "ERROR")
                    res["last_live_verdict"] = st
                    # Alive if checkout responded (e.g. DECLINED, APPROVED, 3DS, etc)
                    if not str(st).startswith("ERROR"):
                        res["verified"] = True
                        res["status"] = "VERIFIED_LIVE"
                    else:
                        res["verified"] = False
                        res["status"] = f"CHECK_FAIL: {st}"
                except Exception as e:
                    res["verified"] = False
                    res["status"] = f"CHECK_EXC: {type(e).__name__}"
                    res["last_live_verdict"] = f"ERROR: {type(e).__name__}"
        except Exception as e:
            res["status"] = f"EXC: {type(e).__name__}"
            res["last_live_verdict"] = f"ERROR: {type(e).__name__}"
            
        return res

async def main():
    sem = asyncio.Semaphore(6)
    tasks = [process_domain(d, sem) for d in DOMAINS]
    results = await asyncio.gather(*tasks)
    
    print(f"{'Domain':32} | {'Cents':6} | {'Cur':4} | {'Status':16} | {'Verdict':20} | Title")
    print("-" * 105)
    for r in sorted(results, key=lambda x: (x.get('cheapest_cents') or 999999)):
        c = r.get('cheapest_cents')
        c_str = f"{c}c" if c is not None else "-"
        print(f"{r['domain']:32} | {c_str:6} | {r['currency']:4} | {r['status']:16} | {str(r['last_live_verdict'])[:20]:20} | {r.get('title','')[:25]}")
        
    with open("scratch/_qualify_35_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
