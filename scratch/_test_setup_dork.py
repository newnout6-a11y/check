import asyncio
import sys, os
sys.path.insert(0, os.path.abspath("."))
import recon

queries = [
    'inurl:/my-account/ Register "Lost your password"',
    'inurl:/my-account/ "woocommerce-register-nonce"',
    'inurl:/my-account/ "Register" "Username or email address"',
    'inurl:/my-account/ "A link to set a new password"',
    'inurl:/my-account/ "add-payment-method"',
]

async def test():
    for q in queries:
        doms, imp = await recon._ddg_query_rotating(q)
        print(f"Query: {q}")
        print(f"  Results ({imp}): {len(doms)}")
        for d in doms[:5]:
            print(f"   {d}")
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(test())
