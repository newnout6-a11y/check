# -*- coding: utf-8 -*-
import sys, pathlib, random
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config, gate_client as gc
print("config salt      :", config.STRIPE_JS_BUILD)
t = gc.stripe_telemetry("https://example.com", "pk_live_x")
print("payment_user_agent:", t["payment_user_agent"])
p = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
card = f"{p['number']}|{p['mm']}|{p['yy']}|{p['cvc']}"
print("probe card       :", card)
print("luhn ok          :", gc.check_luhn(p["number"]))
print("coerce/refundable:", config.coerce_verdict("CHALLENGE_FAILED"), config.coerce_verdict("INVALID_URL"), config.is_refundable("CHALLENGE_BURNED"))
pathlib.Path("_audit/_probe_card.txt").write_text(card, encoding="utf-8")
