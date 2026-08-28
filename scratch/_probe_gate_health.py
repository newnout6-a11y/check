# -*- coding: utf-8 -*-
# Лёгкая живость-проба гейтов бота: DNS + GET витрины (Stage-1 style, без карт/регистрации)
import asyncio, json, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from curl_cffi.requests import AsyncSession

TARGETS = {
    "setupwoo": ["www.blackbeltprotein.com.au"],
    "store_verified": ["essexmonastery.com", "rocketgeek.com", "thimpress.com",
                       "pianowizardacademy.com", "theposhpundit.co.uk", "wellyou.lt",
                       "themakersclub.it", "tricolistica.com"],
    "store_random_sample": ["wisdomofplanets.com", "conferenziaworld.com", "woo.com",
                            "herbaura.fr", "cherryarts.org", "madatshop.com",
                            "senseilms.com", "woocommerce.com"],
}

async def probe(sem, domain, results):
    async with sem:
        t0 = time.perf_counter()
        out = {"domain": domain, "dns": False, "http": None, "latency_ms": None,
               "cf": False, "woo_api": None, "stripe_pk": False}
        try:
            import socket
            socket.gethostbyname(domain)
            out["dns"] = True
        except Exception:
            results.append(out); return
        try:
            async with AsyncSession(impersonate="chrome131", verify=False, timeout=10) as s:
                r = await s.get(f"https://{domain}/", timeout=10)
                out["http"] = r.status_code
                out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                html = r.text[:200000]
                out["cf"] = ("Just a moment..." in r.text) or ("challenge-platform" in r.text)
                out["stripe_pk"] = "pk_live_" in html
                # Store API nonce-проба: GET /wp-json/wc/store/v1/cart
                try:
                    r2 = await s.get(f"https://{domain}/wp-json/wc/store/v1/cart", timeout=8)
                    nt = r2.headers.get("nonce") or r2.headers.get("Nonce") or ""
                    out["woo_api"] = f"{r2.status_code}" + (f"+nonce" if nt else "")
                except Exception as e:
                    out["woo_api"] = type(e).__name__
        except Exception as e:
            out["http"] = "ERR:" + type(e).__name__
            out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        results.append(out)

async def main():
    results = []
    sem = asyncio.Semaphore(10)
    tasks = []
    for grp, doms in TARGETS.items():
        for d in doms:
            tasks.append(probe(sem, d, results))
    await asyncio.gather(*tasks)
    by = {r["domain"]: r for r in results}
    for grp, doms in TARGETS.items():
        print(f"=== {grp} ===")
        for d in doms:
            r = by[d]
            print(f"  {d:36} dns={r['dns']} http={str(r['http']):8} {str(r['latency_ms']):6}ms "
                  f"cf={r['cf']} pk={r['stripe_pk']} store_api={r['woo_api']}")
    with open("scratch/_gate_health_probe.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("[*] saved scratch/_gate_health_probe.json")

asyncio.run(main())
