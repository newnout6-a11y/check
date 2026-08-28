# language: python, file: scratch/_finalize_pool.py — итоговый пул: store (verified) +
# setup (blackbeltprotein) + mint-гейты (PI_MINTED) в data/final_gates.json
import json

store = json.load(open("data/store_gates.json", encoding="utf-8"))
ready = json.load(open("data/ready_gates.json", encoding="utf-8"))

verified_store = [g for g in store if g.get("verified")]
mint_store = [g for g in store
              if not g.get("verified") and g.get("verify_status") == "APPROVED@PAID"]

pool = []
for g in ready:
    e = dict(g)
    e["vector"] = "setup_intent"
    pool.append(e)
for g in verified_store:
    e = {
        "domain": g["domain"],
        "base_url": g["base_url"],
        "pk_live": g.get("pk_live", ""),
        "gate_type": "woo_store_api",
        "vector": "store_confirm",
        "verify_status": g.get("verify_status", ""),
        "cheapest_cents": g.get("cheapest_cents"),
        "updated_at": g.get("updated_at"),
        "status": "READY",
    }
    pool.append(e)
for g in mint_store:
    e = {
        "domain": g["domain"],
        "base_url": g["base_url"],
        "pk_live": g.get("pk_live", ""),
        "gate_type": "woo_store_mint",
        "vector": "pi_mint",
        "verify_status": g.get("verify_status", ""),
        "updated_at": g.get("updated_at"),
        "status": "READY",
    }
    pool.append(e)

with open("data/final_gates.json", "w", encoding="utf-8") as f:
    json.dump(pool, f, indent=2, ensure_ascii=False)

print(f"setup_intent gates: {len(ready)}")
print(f"store_confirm gates (emitter verdict): {len(verified_store)}")
print(f"  -> " + ", ".join(g['domain'] for g in verified_store))
print(f"pi_mint gates (PI_MINTED): {len(mint_store)}")
print(f"  -> " + ", ".join(g['domain'] for g in mint_store))
print(f"\nTOTAL POOL: {len(pool)}")
