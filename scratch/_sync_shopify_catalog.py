# -*- coding: utf-8 -*-
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_PATH = os.path.join(ROOT, "data", "shopify_gates.json")
TARGETS_PATH = os.path.join(ROOT, "data", "shopify_targets.txt")
RESULTS_PATH = os.path.join(ROOT, "scratch", "_qualify_35_results.json")

def main():
    with open(GATES_PATH, "r", encoding="utf-8") as f:
        gates = json.load(f)

    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        qual_results = json.load(f)

    existing_domains = {g["domain"]: g for g in gates if "domain" in g}
    
    new_entries = []
    for r in qual_results:
        d = r["domain"]
        if d in existing_domains:
            continue
        
        url = r.get("url") or f"https://{d}"
        cheapest_cents = r.get("cheapest_cents")
        currency = r.get("currency") or "USD"
        status = r.get("status")
        verdict = r.get("last_live_verdict") or "ERROR"
        title = r.get("title") or ""
        
        entry = {
            "url": url,
            "domain": d,
            "cheapest_cents": cheapest_cents,
            "currency": currency,
            "last_live_check": "2026-09-07",
            "last_live_verdict": verdict,
        }
        if title:
            entry["cheapest_product"] = title
            
        if status == "VERIFIED_LIVE":
            entry["verified"] = True
        elif status == "OVER_CAP":
            entry["verified"] = True
            entry["over_cap"] = True
            entry["note"] = f"catalogue over $20 cap ({cheapest_cents}c)"
        else: # failed / dead
            entry["verified"] = False
            entry["dead_surface"] = True
            entry["note"] = status
            
        new_entries.append(entry)

    print(f"Adding {len(new_entries)} new entries to shopify_gates.json...")
    updated_gates = gates + new_entries
    
    with open(GATES_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_gates, f, indent=2, ensure_ascii=False)
        
    print(f"Total entries in shopify_gates.json: {len(updated_gates)}")
    
    # Now build clean shopify_targets.txt
    # Rule: strictly verified stores under $20 cap (<= 2000 cents)
    verified_under_cap = [
        g for g in updated_gates
        if g.get("verified") is True
        and not g.get("over_cap")
        and not g.get("dead_surface")
        and not g.get("phantom")
        and not g.get("blocked")
        and g.get("cheapest_cents") is not None
        and g.get("cheapest_cents") <= 2000
    ]
    
    # Sort with cheapest first or keep existing order?
    # Let's keep URLs properly formatted: https://domain
    urls = [g["url"].rstrip("/") for g in verified_under_cap]
    
    # Ensure no duplicates
    seen = set()
    unique_urls = []
    for u in urls:
        clean_u = u.replace("http://", "https://")
        if clean_u not in seen:
            seen.add(clean_u)
            unique_urls.append(clean_u)
            
    print(f"Total verified targets under cap for shopify_targets.txt: {len(unique_urls)}")
    
    with open(TARGETS_PATH, "w", encoding="utf-8") as f:
        for u in unique_urls:
            f.write(u + "\n")
            
    print("shopify_targets.txt successfully updated.")

if __name__ == "__main__":
    main()
