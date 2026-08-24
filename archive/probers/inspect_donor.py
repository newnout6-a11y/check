# language: Python 3.12+, file: inspect_donor.py, target: Windows 11
import asyncio
import re
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

CANDIDATES = [
    "https://thetrendywhippet.co.uk",
    "https://lifterlms.com",
    "https://wisdomofplanets.com",
    "https://rocketgeek.com"
]

PATHS = [
    "/my-account/add-payment-method/",
    "/my-account/",
    "/checkout/",
]


async def inspect_target(url):
    print(f"\n==================== INSPECTING: {url} ====================", flush=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for path in PATHS:
            target = url + path
            try:
                async with s.get(target, ssl=False, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    text = await r.text(errors="replace")
                    print(f"[{r.status}] {target} (len={len(text)}, final={r.url})", flush=True)
                    
                    # Look for pk_live
                    pks = re.findall(r'pk_live_[0-9a-zA-Z]{24,}', text)
                    if pks:
                        print(f"  -> pk_live ({len(pks)}): {pks[0]}", flush=True)
                        
                    # Look for nonces
                    for n in [
                        "woocommerce-register-nonce",
                        "createAndConfirmSetupIntentNonce",
                        "add_card_nonce",
                        "woocommerce-add-payment-method-nonce",
                        "woocommerce-process-checkout-nonce",
                        "wc_stripe_params",
                        "wc_stripe_upe_params"
                    ]:
                        matches = re.findall(rf'{n}["\']?\s*[:=]\s*["\']([^"\']+)["\']', text, re.I)
                        if matches:
                            print(f"  -> {n}: {matches[0]}", flush=True)
                        elif n in text:
                            print(f"  -> {n}: [PRESENT in text]", flush=True)
            except Exception as e:
                print(f"[-] {target} error: {e}", flush=True)


async def main():
    for c in CANDIDATES:
        await inspect_target(c)


if __name__ == "__main__":
    asyncio.run(main())
