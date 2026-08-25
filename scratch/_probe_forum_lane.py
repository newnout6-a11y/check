# language: Python 3.12+, file: scratch/_probe_forum_lane.py, target: Windows 11
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

import harvest_donors as hd


async def probe():
    async with aiohttp.ClientSession(headers={"User-Agent": hd.UA},
                                     connector=aiohttp.TCPConnector(ssl=False)) as s:
        topics = await hd.extract_thread_links(s, 'woocommerce-gateway-stripe', max_pages=2)
        print(f"forum lane live: {len(topics)} topics from slug woocommerce-gateway-stripe (2 pages)")
        if topics:
            sem = asyncio.Semaphore(1)
            doms, prio = await hd.extract_domains_from_topic(s, topics[0], sem)
            print(f"  first topic -> {len(doms)} domains ({len(prio)} priority)")
            return True
    return False


ok = asyncio.run(probe())
print("FORUM LANE:", "OK" if ok else "EMPTY (wordpress.org layout change?)")
