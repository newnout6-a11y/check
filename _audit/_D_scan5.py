# language: Python 3.14, file: _audit/_D_scan5.py
import sys, json, pathlib
sys.path.insert(0, ".")
from collections import Counter
def load(n): return json.loads((pathlib.Path("data")/n).read_text(encoding="utf-8"))
def txt(n):
    p = pathlib.Path("data")/n
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if p.exists() else []
sp = load("scout_pool.json"); st_txt = [x.rstrip("/").replace("https://","") for x in txt("store_targets.txt")]
print("scout domains in store_targets:", len({g.get("domain") for g in sp} & set(st_txt)), "of", len(st_txt))
imp = load("_imp_ab.json")
print("_imp_ab keys:", list(imp)[:10] if isinstance(imp, dict) else len(imp))
print("_imp_ab sample:", json.dumps(imp, ensure_ascii=False)[:400])
for n in ("_r10_dork_probe.json","_r10_dork_probe2.json"):
    d = load(n)
    print(n, "type", type(d).__name__, "len", len(d) if hasattr(d,"__len__") else "-", "sample:", json.dumps(d, ensure_ascii=False)[:250])
ready = load("ready_gates.json")
import datetime
print("ready_gates upe_nonce:", ready[0].get("upe_nonce"), "updated:", datetime.datetime.fromtimestamp(ready[0]["updated_at"]).isoformat(), "battle_check:", ready[0].get("battle_check"))
fg = load("final_gates.json")
print("final_gates:", [(g.get("domain"), g.get("vector"), g.get("last_live_check")) for g in fg])
ht = txt("hit_targets.txt")
print("hit_targets:", len(ht), "hosts:", dict(Counter(u.split("/")[2] if "//" in u else u.split("/")[0] for u in ht)))
print("--- LIVE PROBE of hit_targets ---")
try:
    import stripe_fid
    from curl_cffi.requests import Session
    s = Session(impersonate="chrome136", verify=False)
    for u in ht[:10]:
        try:
            pk, cs = "", ""
            d = stripe_fid.decode_fragment(u)
            if isinstance(d, dict):
                pk = str(d.get("apiKey") or d.get("key") or "")
                cs = str(d.get("checkoutSessionId") or d.get("sessionId") or "")
            if not cs:
                import re
                m = re.search(r"(cs_live_[A-Za-z0-9]+)", u)
                cs = m.group(1) if m else ""
                m2 = re.search(r"(pk_live_[A-Za-z0-9]+)", u)
                pk = pk or (m2.group(1) if m2 else "")
            if not (pk and cs):
                print("  DECODE_FAIL", u[:60]); continue
            r = s.get(f"https://api.stripe.com/v1/payment_pages/{cs}", params={"key": pk},
                      headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/"}, timeout=12)
            body = {}
            try: body = r.json()
            except Exception: body = {"raw": r.text[:120]}
            pi = body.get("payment_intent") or {}
            print(f"  HTTP={r.status_code} session_status={body.get('status')} pi={pi.get('status')} live={body.get('livemode')} err={str(body.get('error'))[:90]} cs={cs[:18]}")
        except Exception as e:
            print("  EXC", type(e).__name__, str(e)[:100])
except Exception as e:
    print("PROBE SETUP FAIL", type(e).__name__, e)
