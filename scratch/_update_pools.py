import json
import time

# 1. Update store_gates.json
sg_path = "data/store_gates.json"
store_gates = json.load(open(sg_path, "r", encoding="utf-8"))
existing_sg = {g["domain"]: g for g in store_gates}

new_store = [
    {
        "domain": "yarnstreet.com",
        "base_url": "https://yarnstreet.com",
        "pk_live": "pk_live_51PpsY1C04hU1Uu1R",
        "gate_type": "woo_store_api",
        "store_nonce": True,
        "cheapest_cents": 90,
        "updated_at": int(time.time()),
        "status": "STORE_LIVE",
        "verified": True,
        "verify_status": "DECLINED",
        "verify_detail": "There was an error processing the payment: Your card was declined.",
        "phantom": False,
        "phantom_probe": "DECLINED: Your card was declined.",
        "dead_surface": False,
        "battle_check": "2026-09-02",
        "battle_result": "LIVE (cap $20)"
    },
    {
        "domain": "specialteacompany.com",
        "base_url": "https://specialteacompany.com",
        "pk_live": "pk_live_51Nw9sY1",
        "gate_type": "woo_store_api",
        "store_nonce": True,
        "cheapest_cents": 822,
        "updated_at": int(time.time()),
        "status": "STORE_LIVE",
        "verified": True,
        "verify_status": "DECLINED",
        "verify_detail": "There was an error processing the payment: The card was declined.",
        "phantom": False,
        "phantom_probe": "DECLINED: The card was declined.",
        "dead_surface": False,
        "battle_check": "2026-09-02",
        "battle_result": "LIVE (cap $20)"
    }
]

for ng in new_store:
    if ng["domain"] in existing_sg:
        existing_sg[ng["domain"]].update(ng)
    else:
        store_gates.insert(0, ng)

with open(sg_path, "w", encoding="utf-8") as f:
    json.dump(store_gates, f, indent=2, ensure_ascii=False)
print("Updated store_gates.json with new verified gates.")

# 2. Update shopify_gates.json
sh_path = "data/shopify_gates.json"
shopify_gates = json.load(open(sh_path, "r", encoding="utf-8"))
existing_sh = {g["domain"]: g for g in shopify_gates}

new_shopify = [
    {
        "url": "https://barenakedwools.com",
        "domain": "barenakedwools.com",
        "cheapest_cents": 1,
        "cheapest_title": "Digital pattern / yarn card",
        "variant_id": None,
        "currency": "USD",
        "verified": True,
        "last_live_check": "2026-09-02",
        "last_live_verdict": "DECLINED"
    },
    {
        "url": "https://barrettwoolco.com",
        "domain": "barrettwoolco.com",
        "cheapest_cents": 195,
        "cheapest_title": "Wool sample card",
        "variant_id": None,
        "currency": "USD",
        "verified": True,
        "last_live_check": "2026-09-02",
        "last_live_verdict": "DECLINED"
    },
    {
        "url": "https://loopyarn.com",
        "domain": "loopyarn.com",
        "cheapest_cents": 300,
        "cheapest_title": "Yarn swatch",
        "variant_id": None,
        "currency": "USD",
        "verified": True,
        "last_live_check": "2026-09-02",
        "last_live_verdict": "DECLINED"
    },
    {
        "url": "https://artisanduchocolat.com",
        "domain": "artisanduchocolat.com",
        "cheapest_cents": 500,
        "cheapest_title": "Chocolate sample",
        "variant_id": None,
        "currency": "USD",
        "verified": True,
        "last_live_check": "2026-09-02",
        "last_live_verdict": "DECLINED"
    },
    {
        "url": "https://badsheepyarn.com",
        "domain": "badsheepyarn.com",
        "cheapest_cents": 695,
        "cheapest_title": "Mini skein",
        "variant_id": None,
        "currency": "USD",
        "verified": True,
        "last_live_check": "2026-09-02",
        "last_live_verdict": "DECLINED"
    }
]

for ng in new_shopify:
    if ng["domain"] in existing_sh:
        existing_sh[ng["domain"]].update(ng)
    else:
        shopify_gates.insert(0, ng)

with open(sh_path, "w", encoding="utf-8") as f:
    json.dump(shopify_gates, f, indent=2, ensure_ascii=False)
print("Updated shopify_gates.json with new verified gates.")
