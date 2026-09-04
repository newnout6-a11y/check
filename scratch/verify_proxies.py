# language: Python 3.12+, file: scratch/verify_proxies.py, target: Windows 11
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))
from curl_cffi.requests import AsyncSession
import gate_client as gc


async def check_proxy(proxy: str, sem: asyncio.Semaphore, results: list):
    async with sem:
        t0 = time.perf_counter()
        try:
            async with AsyncSession(impersonate="chrome124", verify=False, proxy=proxy) as s:
                r = await s.get("https://api.ipify.org/?format=json", timeout=4.5)
                if r.status_code == 200 and "ip" in r.text:
                    lat = int((time.perf_counter() - t0) * 1000)
                    results.append({
                        "url": proxy,
                        "alive": True,
                        "latency_ms": lat,
                        "fail_count": 0,
                        "last_check": int(time.time()),
                    })
                    print(f"[+] ALIVE: {proxy} ({lat}ms)")
        except Exception:
            pass


async def main():
    source_file = r"C:\Users\Redmi\.gemini\antigravity\brain\2db8c2a8-7c93-4c38-b82b-b0d3166a117c\.user_uploaded\media_1788452916738.txt"
    with open(source_file, "r", encoding="utf-8") as f:
        raw = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    candidates = []
    seen = set()
    for l in raw:
        norm = gc.normalize_proxy(l)
        if norm and norm not in seen:
            seen.add(norm)
            candidates.append(norm)

    print(f"Total candidates: {len(candidates)}. Probing top 350 proxies in 60 threads...")
    sem = asyncio.Semaphore(60)
    results = []
    tasks = [check_proxy(p, sem, results) for p in candidates[:350]]
    await asyncio.gather(*tasks)
    print(f"Probing complete! Found {len(results)} verified alive proxies.")

    if results:
        results.sort(key=lambda x: x["latency_ms"])
        print("Top verified proxies:")
        for r in results[:10]:
            print(f"  {r['url']} - {r['latency_ms']}ms")

        # Save ONLY the verified live ones to data/proxies.txt and data/proxy_health.json
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "proxies.txt"), "w", encoding="utf-8") as f:
            for r in results:
                f.write(r["url"] + "\n")

        with open(os.path.join("data", "proxy_health.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print("Updated data/proxies.txt and data/proxy_health.json with verified working proxies only.")
    else:
        print("[!] No public proxies responded. Keeping pool direct so checks never fail.")
        with open(os.path.join("data", "proxies.txt"), "w", encoding="utf-8") as f:
            pass
        if os.path.exists(os.path.join("data", "proxy_health.json")):
            os.remove(os.path.join("data", "proxy_health.json"))


if __name__ == "__main__":
    asyncio.run(main())
