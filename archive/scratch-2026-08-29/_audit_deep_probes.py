# language: Python 3.12+, file: scratch/_audit_deep_probes.py
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import gate_client as gc
import setup_gate
from bot.utils import formatter


async def test_unit_suite():
    print("=== 1. LUHN & CARD PARSER TESTS ===")
    assert gc.check_luhn("") is False, "Luhn empty should be False"
    assert gc.check_luhn("abc") is False, "Luhn letters should be False"
    assert gc.check_luhn("123") is False, "Luhn short should be False"
    assert gc.check_luhn("4937241006643332") is True, "Luhn valid should be True"
    assert gc.check_luhn("4937241006643333") is False, "Luhn invalid should be False"
    print("OK: check_luhn checks passed.")

    # parse_card
    c1 = gc.parse_card("4937241006643332|02|31|275")
    assert c1["number"] == "4937241006643332" and c1["month"] == "02" and c1["year"] == "2031" and c1["cvc"] == "275"
    assert "mm" in c1 and "yy" in c1
    
    c2 = gc.parse_card("4937241006643332 02 31 275")
    assert c2["number"] == "4937241006643332" and c2["month"] == "02" and c2["year"] == "2031" and c2["cvc"] == "275"

    c3 = gc.parse_card("4937241006643332:02:31:275")
    assert c3["number"] == "4937241006643332" and c3["month"] == "02"

    c4 = gc.parse_card("4937241006643332/02/31/275")
    assert c4["number"] == "4937241006643332" and c4["month"] == "02"
    print("OK: parse_card multi-format checks passed.")

    # extract_pan / fmt_pan
    assert formatter.extract_pan("4937241006643332|02|31|275") == "4937241006643332"
    assert formatter.fmt_pan("4937241006643332|02|31|275") == "4937 24** **** 3332"
    assert formatter.fmt_pan("5378721105858595 04 29 528") == "5378 72** **** 8595"
    print("OK: extract_pan / fmt_pan checks passed.")

    # detail translation
    assert formatter.translate_detail("Your card was declined.") == "Карта отклонена банком-эмитентом."
    assert formatter.translate_detail("Your card has insufficient funds.") == "Недостаточно средств на карте."
    assert formatter.translate_detail("Your card's security code is incorrect.") == "Неверный CVC/CVV код."
    assert "[100c USD]" in formatter.translate_detail("[100c USD] Your card was declined.")
    print("OK: detail translation checks passed.")


async def test_live_bin_lookup():
    print("\n=== 2. LIVE BIN LOOKUP TEST ===")
    binfo = await gc.bin_lookup_enriched("493724")
    print(f"BIN 493724: scheme={binfo.get('scheme')}, type={binfo.get('type')}, country={binfo.get('country')}, bank={binfo.get('bank')}, is_vbv={binfo.get('is_vbv')}")
    assert binfo.get("scheme"), "BIN scheme should be resolved"
    summary = setup_gate.bin_summary(binfo)
    print(f"BIN Summary: {summary}")
    print("OK: Live BIN lookup passed.")


async def test_live_setup_donor():
    print("\n=== 3. LIVE SETUPINTENT DONOR PROBE ===")
    gates = setup_gate.load_ready_gates()
    assert gates, "Gate pool must not be empty"
    donor = gates[0]
    dom = donor.get("domain") or donor.get("base_url")
    print(f"Testing donor: {dom}...")
    gs = setup_gate.GateSession(donor)
    ok, detail = await gs.open()
    print(f"Session open result: ok={ok}, detail={detail}")
    if ok:
        probe = gc.gen_probe_card()
        raw = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
        print(f"Checking probe card {gc.mask_pan(raw)}...")
        res = await gs.check_card(raw)
        print(f"Verdict: {res.get('status')} | Detail: {res.get('detail')}")
        await gs.close()
        assert res.get("status") in config.VERDICTS, f"Verdict {res.get('status')} must be in taxonomy"
        print("OK: Live SetupIntent probe succeeded with valid verdict.")
    else:
        print(f"WARNING: Donor session open failed: {detail}")


async def main():
    await test_unit_suite()
    await test_live_bin_lookup()
    await test_live_setup_donor()
    print("\nALL AUDIT PROBES COMPLETE.")


if __name__ == "__main__":
    asyncio.run(main())
