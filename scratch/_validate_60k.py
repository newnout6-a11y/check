# -*- coding: utf-8 -*-
# Валидация большого прокси-листа: 60k HTTPs _ PROXIES (2).txt -> data/proxies.txt
import asyncio, os, re, sys, time
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curl_cffi.requests import AsyncSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '60k HTTPs _ PROXIES (2).txt')
OUT = os.path.join(ROOT, 'data', 'proxies.txt')
PROBE = "https://api.ipify.org/?format=json"

def load_candidates():
    seen, out = set(), []
    with open(SRC, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            m = re.match(r"^\s*(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\s*$", ln)
            if m:
                p = m.group(1)
                if p not in seen:
                    seen.add(p)
                    out.append(p)
    return out

async def check(sem, proxy, results):
    async with sem:
        try:
            async with AsyncSession(impersonate="chrome131", verify=False,
                                    proxy=f"http://{proxy}", timeout=8) as s:
                r = await s.get(PROBE, timeout=8)
                if r.status_code == 200:
                    results.append(proxy)
        except Exception:
            pass

async def main():
    cands = load_candidates()
    print(f"[*] уникальных ip:port из файла: {len(cands)}", flush=True)
    sem = asyncio.Semaphore(100)
    alive = []
    t0 = time.time()
    CH = 5000
    for i in range(0, len(cands), CH):
        chunk = cands[i:i + CH]
        part = []
        await asyncio.gather(*[check(sem, p, part) for p in chunk])
        alive.extend(part)
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(alive) + "\n")
        rate = (i + len(chunk)) / max(time.time() - t0, 1)
        print(f"  [chunk {i + len(chunk)}/{len(cands)}] живых: {len(alive)} "
              f"({len(alive) / (i + len(chunk)) * 100:.1f}%), {rate:.0f} прокс/с", flush=True)
    print(f"[+] ГОТОВО: {len(alive)} живых из {len(cands)} -> {OUT}", flush=True)

asyncio.run(main())