import asyncio
import json
import aiohttp

CARD = "5175465382242090|09|2030|018"

async def bin_lookup(bin_num):
    headers = {"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        try:
            async with s.get(f"https://lookup.binlist.net/{bin_num}") as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            pass
        try:
            async with s.get(f"https://data.handyapi.com/bin/{bin_num}") as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            pass
    return None

async def main():
    binfo = await bin_lookup(CARD[:6])
    print(f"BIN INFO ({CARD[:6]}):", json.dumps(binfo, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
