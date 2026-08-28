import asyncio
import re
from curl_cffi.requests import AsyncSession

async def inspect_more_js():
    targets = [
        "/cdn/shopifycloud/checkout-web/assets/c1/component-CreateCreditCard.C-yID4FT.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/PaymentMethods.W_eR1SBI.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/graphql-utilities.Jjmwu6tT.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/page-Payment.Cjo9iUBZ.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/hooks-useGeneralPaymentErrorMessage.Fjeuus4C.js",
        "/cdn/shopifycloud/checkout-web/assets/c1/PaymentErrorBanner.CmoUV2Xl.js",
    ]
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        for t in targets:
            url = f"https://cdn.shopify.com{t}"
            r = await s.get(url)
            print(f"\n=================== {t} ===================")
            # Find GraphQL operations
            ops = re.findall(r'(?:mutation|query)\s+([a-zA-Z0-9_]+)\s*(\([^\)]*\))?\s*\{', r.text)
            print(f"GraphQL Ops: {ops}")
            
            # Find error codes / messages
            errors = re.findall(r'["\']([A-Z_]{4,30})["\']', r.text)
            err_set = set(e for e in errors if any(w in e for w in ["PAYMENT", "CARD", "DECLINE", "FAIL", "REJECT", "FRAUD", "ERROR", "INVALID", "EXPIRED", "3DS", "AUTH"]))
            print(f"Error constants: {sorted(list(err_set))[:15]}")
            
            # Find HTTP endpoints
            urls = re.findall(r'["\'](/checkouts/[^"\']+|/api/[^"\']+|https?://[^"\']+)["\']', r.text)
            print(f"Endpoints/URLs: {list(set(urls))[:5]}")

if __name__ == "__main__":
    asyncio.run(inspect_more_js())
