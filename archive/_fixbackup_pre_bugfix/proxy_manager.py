# language: Python 3.12+, file: proxy_manager.py, target: Windows 11, deps: curl_cffi
# Sprint 3.5: пул прокси с авто-валидацией, sticky-привязкой к донору и health-файлом.
import asyncio
import json
import os
import random
import time

from curl_cffi.requests import AsyncSession

import gate_client as gc

HEALTH_FILE = os.path.join("data", "proxy_health.json")
PROBE_URL = "https://api.ipify.org/?format=json"
VALIDATE_INTERVAL = 30 * 60  # сек между фоновыми ревалидациями


class ProxyPool:
    """alive/dead по фактам запроса, sticky по ключу (домен донора):
    одна сессия донора = один IP на весь прогон карт."""

    def __init__(self, proxies: list[str] | None = None):
        self.entries: list[dict] = []
        for url in proxies or []:
            self.entries.append({"url": url, "alive": True, "latency_ms": None,
                                 "fail_count": 0, "last_check": 0})
        self._sticky: dict[str, str] = {}
        self._load_health()

    # --- persistence ---

    def _load_health(self):
        if not os.path.exists(HEALTH_FILE):
            return
        try:
            with open(HEALTH_FILE, encoding="utf-8") as f:
                saved = {h["url"]: h for h in json.load(f)}
            for e in self.entries:
                h = saved.get(e["url"])
                if h:
                    e.update({k: h[k] for k in ("latency_ms", "fail_count") if k in h})
                    # alive из прошлого прогона не доверяем — валидация решает заново
        except Exception:
            pass

    def _save_health(self):
        os.makedirs("data", exist_ok=True)
        try:
            with open(HEALTH_FILE, "w", encoding="utf-8") as f:
                json.dump([{k: e[k] for k in ("url", "latency_ms", "fail_count", "last_check")}
                           for e in self.entries], f, indent=2)
        except Exception:
            pass

    # --- validation ---

    async def _check_one(self, e: dict, sem: asyncio.Semaphore):
        async with sem:
            t0 = time.perf_counter()
            try:
                async with AsyncSession(impersonate="chrome131", verify=False,
                                        proxy=e["url"]) as s:
                    r = await s.get(PROBE_URL, timeout=10)
                    ok = r.status_code == 200
            except Exception:
                ok = False
            lat = int((time.perf_counter() - t0) * 1000)
            e["last_check"] = int(time.time())
            if ok:
                e["alive"] = True
                e["latency_ms"] = lat
                e["fail_count"] = 0
            else:
                e["fail_count"] += 1
                if e["fail_count"] >= 3:
                    e["alive"] = False

    async def validate_all(self) -> tuple[int, int]:
        sem = asyncio.Semaphore(20)
        await asyncio.gather(*[self._check_one(e, sem) for e in self.entries])
        self._save_health()
        alive = sum(1 for e in self.entries if e["alive"])
        return alive, len(self.entries)

    # --- selection ---

    def _weights(self) -> list[float]:
        return [1.0 / max(e.get("latency_ms") or 1000, 100) for e in self.entries]

    def pick(self, sticky_key: str | None = None) -> str | None:
        alive = [e for e in self.entries if e["alive"]]
        if not alive:
            return None
        if sticky_key and sticky_key in self._sticky:
            url = self._sticky[sticky_key]
            if any(e["url"] == url for e in alive):
                return url
            self._sticky.pop(sticky_key, None)
        chosen = random.choices(alive, weights=[1.0 / max(e.get("latency_ms") or 1000, 100)
                                                for e in alive], k=1)[0]
        if sticky_key:
            self._sticky[sticky_key] = chosen["url"]
        return chosen["url"]

    def mark_bad(self, proxy_url: str | None):
        if not proxy_url:
            return
        for e in self.entries:
            if e["url"] == proxy_url:
                e["fail_count"] += 1
                if e["fail_count"] >= 3:
                    e["alive"] = False
                    for k, v in list(self._sticky.items()):
                        if v == proxy_url:
                            self._sticky.pop(k)
        self._save_health()

    def status_line(self) -> str:
        alive = sum(1 for e in self.entries if e["alive"])
        lats = sorted(e["latency_ms"] for e in self.entries
                      if e["alive"] and e.get("latency_ms"))
        med = lats[len(lats) // 2] if lats else 0
        return f"{alive}/{len(self.entries)} alive, median {med}ms"


async def maybe_pool(explicit_proxy: str | None) -> tuple[ProxyPool | None, str | None]:
    """Единая точка входа для CLI: явный --proxy приоритетен; иначе валидированный пул."""
    if explicit_proxy:
        return None, gc.pick_proxy(None, explicit_proxy)
    pool_raw = gc.load_proxies()
    if not pool_raw:
        return None, None
    pp = ProxyPool(pool_raw)
    alive, total = await pp.validate_all()
    print(f"[*] Proxy validation: {pp.status_line()}")
    if alive == 0:
        print("[!] All proxies dead — running direct")
        return pp, None
    return pp, None


if __name__ == "__main__":
    async def _main():
        pp, _ = await maybe_pool(None)
        if pp:
            print("[*] sample picks:", pp.pick("donor-a"), "|", pp.pick())
    asyncio.run(_main())
