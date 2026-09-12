
import asyncio, pathlib, sys
sys.path.insert(0, ".")
import stripe_fid, gate_client as gc
from curl_cffi.requests import AsyncSession
line = [l for l in pathlib.Path("data/hit_targets.txt").read_text(encoding="utf-8").splitlines() if l.strip()][0]
frag = stripe_fid.decode_fragment(line)
pk = frag.get("apiKey") or frag.get("api_key") or ""
cs = frag.get("checkoutSessionId") or frag.get("checkout_session_id") or ""
print("pk:", (pk or "")[:12] + "...", "cs:", (cs or "")[:16] + "...")
async def main():
    async with AsyncSession(impersonate="chrome136", verify=False) as s:
        r = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}", headers={"Authorization": f"Bearer {pk}"}, timeout=20)
        print("HTTP", r.status_code, r.text[:220])
asyncio.run(main())
